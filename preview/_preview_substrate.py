"""Shared substrate helpers for PR preview comparison and highlighting scripts.

Shared by `detect-changed-chapters.py` and `highlight-html-changes.py`.
"""

import re
import subprocess

DEFAULT_NORMALIZE_PATTERNS = (
    # htmlwidgets/plotly mint a fresh random element id on every render.
    r"htmlwidget[-_][0-9a-f]{6,}",
    # Machine-written ISO-8601 datetimes (build stamps), which always carry a
    # time component.
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?",
)

TEXT_SUFFIXES = frozenset({".html", ".htm", ".xml", ".json", ".txt", ".md", ".css", ".js"})

PLACEHOLDER = "GHA-VOLATILE"


class GitError(RuntimeError):
    """A condition that must stop the run rather than degrade silently."""


def run_git(args, repo_dir):
    """Run a git command, raising on any non-zero exit."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace")
        raise GitError(
            f"`git {' '.join(args)}` failed with exit {result.returncode}: {stderr.strip()}"
        )
    return result.stdout


def resolve_deployed_ref(repo_dir, remote, branch):
    """Fetch the deployed branch and return a local ref for it, or None if absent."""
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
    """Read published blob bytes from git."""
    return run_git(["cat-file", "blob", f"{ref}:{path}"], repo_dir)


def compile_patterns(extra_patterns):
    """Compile normalization patterns, rejecting ones that match the empty string."""
    compiled = []
    for raw in [*DEFAULT_NORMALIZE_PATTERNS, *extra_patterns]:
        try:
            pattern = re.compile(raw)
        except re.error as exc:
            raise GitError(f"invalid normalize pattern {raw!r}: {exc}") from exc
        if pattern.search(""):
            raise GitError(
                f"normalize pattern {raw!r} matches the empty string, which would "
                "blank every document"
            )
        compiled.append(pattern)
    return compiled


def normalize(text, patterns, counts=None):
    """Normalize text by blanking volatile patterns."""
    for pattern in patterns:
        if counts is not None:
            text, hits = pattern.subn(PLACEHOLDER, text)
            counts[pattern.pattern] = counts.get(pattern.pattern, 0) + hits
        else:
            text = pattern.sub(PLACEHOLDER, text)
    return text
