#!/usr/bin/env python3
"""Report which rendered chapters differ from the copy published on the deployed branch.

This is the substrate the PR-preview "what changed?" capabilities are built on.
It answers one question -- which rendered chapters differ from the version
currently published on `gh-pages`? -- by comparing this run's render against the
deployed render, never against the source diff.

Ported from `ucdavis/win`'s `.github/scripts/detect-changed-chapters.py`
(MIT, copyright 2025 d-morrison), and rewritten rather than copied:

  * Every git call is checked. The original ran `git fetch` and `git ls-tree`
    with `check=False` and swallowed the comparison in a broad `except`, so a
    network or permission failure yielded "no chapters changed" -- which is
    indistinguishable from a genuinely unchanged PR and silently disables every
    downstream capability. Here a MISSING deployed branch is a stated skip and
    anything else is an error.
  * The answer leaves as a step output rather than through `$GITHUB_ENV`, so it
    is inspectable and testable.
  * The hard-coded `/tmp` scratch path is gone; nothing is materialized to disk.

Configuration (all via the environment, set by `preview/action.yml`):

  RENDERED_DIR         Directory holding this run's rendered site. Required.
  CHAPTER_GLOB         Glob, relative to RENDERED_DIR, selecting the rendered
                       files to compare. Default `chapters/*.html`.
  DEPLOYED_REMOTE      Git remote holding the published site. Default `origin`.
  DEPLOYED_BRANCH      Branch on that remote. Default `gh-pages`.
  DEPLOYED_SUBDIR      Path prefix, within the deployed branch, at which the
                       site root lives. Default '' (the branch root).
  NORMALIZE_PATTERNS   Newline-separated regexes whose matches are blanked
                       before comparison, IN ADDITION to the built-in defaults.
  REPO_DIR             Git repository to run in. Default `.`.
  GITHUB_OUTPUT        Where the step outputs are written, when set.

Outputs:

  detection-status   `compared` or `skipped`
  skip-reason        why the comparison was skipped; empty when compared
  changed-chapters   JSON array of changed chapter ids (a rendered file's path
                     relative to RENDERED_DIR, with its extension removed)
  any-changed        `true` or `false`
"""

import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

from _workflow_annotations import annotate

# Volatility the comparison must see through. Every failure mode of this script
# degrades to "nothing changed", but this one degrades the other way: a page
# that reads as changed on every render makes the whole feature noise.
#
# Deliberately narrow. A bare `YYYY-MM-DD` is NOT matched -- a date in prose is
# real content, and normalizing it would hide a genuine edit.
DEFAULT_NORMALIZE_PATTERNS = (
    # htmlwidgets/plotly mint a fresh random element id on every render.
    r"htmlwidget[-_][0-9a-f]{6,}",
    # Machine-written ISO-8601 datetimes (build stamps), which always carry a
    # time component.
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?",
)

# Suffixes whose contents are text, and so can be normalized before comparison.
# Anything else is compared byte for byte.
TEXT_SUFFIXES = frozenset({".html", ".htm", ".xml", ".json", ".txt", ".md", ".css", ".js"})

PLACEHOLDER = "GHA-VOLATILE"


class DetectionError(RuntimeError):
    """A condition that must stop the run rather than read as 'nothing changed'."""


def run_git(args, repo_dir):
    """Run a git command, raising on any non-zero exit.

    Checked deliberately: the failure this guards against (a fetch that cannot
    reach the remote) is invisible downstream, because its result and a
    genuinely unchanged PR are the same empty list.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace")
        raise DetectionError(
            f"`git {' '.join(args)}` failed with exit {result.returncode}: {stderr.strip()}"
        )
    return result.stdout


def resolve_deployed_ref(repo_dir, remote, branch):
    """Fetch the deployed branch and return a local ref for it, or None if absent.

    Returning None means the branch does not exist on the remote, which is a
    legitimate state (a repository whose first preview has not deployed yet).
    Every other failure -- auth, network, a broken remote -- raises.
    """
    listing = run_git(
        ["ls-remote", "--heads", remote, f"refs/heads/{branch}"], repo_dir
    ).decode("utf-8", "replace")
    if not listing.strip():
        return None

    local_ref = f"refs/gha-preview-base/{branch}"
    run_git(
        [
            "fetch",
            "--no-tags",
            "--depth=1",
            remote,
            f"+refs/heads/{branch}:{local_ref}",
        ],
        repo_dir,
    )
    return local_ref


def published_paths(repo_dir, ref):
    """Every blob path in the deployed tree."""
    listing = run_git(["ls-tree", "-r", "--name-only", "-z", ref], repo_dir)
    return {p for p in listing.decode("utf-8", "replace").split("\0") if p}


def read_published(repo_dir, ref, path):
    return run_git(["cat-file", "blob", f"{ref}:{path}"], repo_dir)


def compile_patterns(extra_patterns):
    """Compile the normalization patterns, rejecting ones that cannot be trusted.

    A pattern that can match the empty string rewrites the whole document into
    placeholders, so every page would read as unchanged -- the silent direction.
    Reject it rather than discovering it as a feature that never fires.
    """
    compiled = []
    for raw in [*DEFAULT_NORMALIZE_PATTERNS, *extra_patterns]:
        try:
            pattern = re.compile(raw)
        except re.error as exc:
            raise DetectionError(f"invalid normalize pattern {raw!r}: {exc}") from exc
        if pattern.search(""):
            raise DetectionError(
                f"normalize pattern {raw!r} matches the empty string, which would "
                "blank every document and report every chapter as unchanged"
            )
        compiled.append(pattern)
    return compiled


def normalize(text, patterns, counts):
    for pattern in patterns:
        text, hits = pattern.subn(PLACEHOLDER, text)
        counts[pattern.pattern] = counts.get(pattern.pattern, 0) + hits
    return text


def contents_differ(rendered_bytes, published_bytes, suffix, patterns, counts):
    if rendered_bytes == published_bytes:
        return False
    if suffix.lower() not in TEXT_SUFFIXES:
        return True
    try:
        rendered_text = rendered_bytes.decode("utf-8")
        published_text = published_bytes.decode("utf-8")
    except UnicodeDecodeError:
        # Not decodable as text after all; the byte comparison above stands.
        return True
    return normalize(rendered_text, patterns, counts) != normalize(
        published_text, patterns, counts
    )


def chapter_id(relative_path):
    """A rendered file's path relative to the render root, without its extension."""
    return relative_path.with_suffix("").as_posix()


def rendered_chapters(rendered_dir, glob):
    return sorted(p for p in rendered_dir.glob(glob) if p.is_file())


def write_outputs(values):
    """Append the step outputs in `$GITHUB_OUTPUT`'s delimiter form.

    Never the bare `key=value` form. Two of these values are free text built
    from things a caller controls -- git's own error wording, and file names,
    which may legitimately contain a newline on POSIX -- so a bare line would
    let one of them declare further outputs of its own.
    """
    output_file = os.getenv("GITHUB_OUTPUT")
    if not output_file:
        return
    delimiter = f"gha-eof-{uuid.uuid4().hex}"
    with open(output_file, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            if delimiter in value:
                raise DetectionError(
                    f"output {key!r} contains the generated delimiter; refusing to "
                    "write an output that could be misread"
                )
            handle.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")


def detect(repo_dir, rendered_dir, glob, remote, branch, subdir, patterns):
    """Return (status, skip_reason, changed_ids)."""
    chapters = rendered_chapters(rendered_dir, glob)
    if not chapters:
        raise DetectionError(
            f"no rendered files matched {glob!r} under {rendered_dir}; the render "
            "is missing or `changed-chapters-glob` does not match this project"
        )

    ref = resolve_deployed_ref(repo_dir, remote, branch)
    if ref is None:
        reason = (
            f"branch {branch!r} does not exist on remote {remote!r}; nothing has "
            "been deployed yet, so there is no published render to compare against"
        )
        print(annotate("notice", f"Skipping changed-chapter detection: {reason}"))
        return "skipped", reason, []

    available = published_paths(repo_dir, ref)
    prefix = subdir.strip("/")
    counts = {}
    changed = []
    new_count = 0

    for chapter in chapters:
        relative = chapter.relative_to(rendered_dir)
        published_path = f"{prefix}/{relative.as_posix()}" if prefix else relative.as_posix()
        identifier = chapter_id(relative)

        if published_path not in available:
            # New in this PR. Reported as changed, never as missing: a page the
            # reader has never seen is the strongest kind of change.
            changed.append(identifier)
            new_count += 1
            print(f"  new:       {identifier}")
            continue

        if contents_differ(
            chapter.read_bytes(),
            read_published(repo_dir, ref, published_path),
            chapter.suffix,
            patterns,
            counts,
        ):
            changed.append(identifier)
            print(f"  changed:   {identifier}")
        else:
            print(f"  unchanged: {identifier}")

    print(
        f"Compared {len(chapters)} rendered file(s) against {branch!r}: "
        f"{len(changed)} changed ({new_count} new)."
    )
    for pattern, hits in sorted(counts.items()):
        if hits:
            print(f"  normalized {hits} match(es) of {pattern!r}")

    if available and new_count == len(chapters):
        # Legitimate for a site whose chapters are all new, and also exactly what
        # a misconfigured `deployed-subdir` looks like -- so say so rather than
        # reporting a clean sweep of changes.
        print(
            annotate(
                "warning",
                "every rendered file was absent from the deployed tree. That is "
                "expected for a brand-new set of chapters, but it is also what a "
                f"wrong `deployed-subdir` looks like (currently {subdir!r}).",
            )
        )

    return "compared", "", changed


def main():
    rendered_dir_raw = os.getenv("RENDERED_DIR", "").strip()
    if not rendered_dir_raw:
        raise DetectionError("RENDERED_DIR is required")
    rendered_dir = Path(rendered_dir_raw)
    if not rendered_dir.is_dir():
        raise DetectionError(f"rendered directory {rendered_dir} does not exist")

    extra_patterns = [
        line.strip()
        for line in os.getenv("NORMALIZE_PATTERNS", "").splitlines()
        if line.strip()
    ]

    status, reason, changed = detect(
        repo_dir=os.getenv("REPO_DIR", ".") or ".",
        rendered_dir=rendered_dir,
        glob=os.getenv("CHAPTER_GLOB", "").strip() or "chapters/*.html",
        remote=os.getenv("DEPLOYED_REMOTE", "").strip() or "origin",
        branch=os.getenv("DEPLOYED_BRANCH", "").strip() or "gh-pages",
        subdir=os.getenv("DEPLOYED_SUBDIR", ""),
        patterns=compile_patterns(extra_patterns),
    )

    write_outputs(
        {
            "detection-status": status,
            "skip-reason": reason,
            "changed-chapters": json.dumps(changed),
            "any-changed": "true" if changed else "false",
        }
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DetectionError as error:
        print(annotate("error", error), file=sys.stderr)
        sys.exit(1)
