#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""
Report content that a merge commit silently dropped.

For every merge commit ``M`` in a range, with parents ``P1``, ``P2`` (and any
further parents of an octopus merge) and merge base ``B``, collect the lines
each side added since ``B`` (``git diff B Pi``, added lines only) and report
those that are absent from ``M``.

That is the signature of a conflict resolved by taking one side of a whole
file ("ours" or "theirs"): every line the other side added in that file
vanishes, while the merge result itself reads as a clean, plausible file that
no content check can fault. A rule saying "resolve hunk by hunk" does not stop
it; this check is the mechanical backstop.

Design notes:
- **A clean merge reports nothing.** A line added on one side since ``B`` is
  new to the history, so the other side cannot have deleted it; a merge that
  keeps both sides' hunks keeps it. Only a resolution that discards one side
  (or an "evil merge" editing content by hand) can drop it.
- **Moved, rewrapped, or bullet-split content is not a drop.** Each file is
  compared as one string with every whitespace run collapsed (and with
  line-leading list item markers optionally stripped), and a line is
  reported only when its normalised text occurs nowhere in ``M``'s tree. So a
  paragraph the resolution moved to another file, rewrapped at different line
  breaks, or split into bullet items, passes.
- **A reworded line is not a drop.** When both sides edited the same line
  and the resolution wrote a third version combining them, neither side's
  line survives verbatim, yet nothing was lost. So a line is reported only
  when no line of ``M``'s copy of the same file that is **new in the merge**
  (not present in any parent) is at least ``MERGE_DROPS_SIMILARITY`` similar
  to it (word-level ``difflib.SequenceMatcher`` ratio, default 0.6; 1 means
  exact matches only). Unrelated lines from other parents or the merge base
  cannot mask a dropped line as a near-twin. A paragraph dropped wholesale
  has no such near-twin.
- **Short and blank lines are skipped** (``MERGE_DROPS_MIN_LENGTH``, default
  20 characters after normalisation): fences, list markers, ``---``, closing
  ``:::`` and similar boilerplate recur everywhere and would add noise
  without evidence.
- **Warn-only by default** (``MERGE_DROPS_FAIL`` defaults to false). A merge
  can legitimately drop a line one side added -- the other side superseded
  it -- so this reports for a human to read rather than blocking. The full
  report goes to the job summary; each affected merge also gets one
  ``::warning::`` annotation. Annotations carry no ``file``/``line``: the
  dropped lines live in a parent's version of the file, not in the checked-out
  tree, so a line number would point at unrelated content.
- **No base ref, or an unreadable range, skips the check** with a warning,
  like the other diff-scoped checks here, instead of walking all of history.

Configuration (environment variables, set by the composite action; the
command-line flags of the same names override them for a local run):
  MERGE_DROPS_BASE_REF      Range start (exclusive). Empty => skip.
  MERGE_DROPS_HEAD_REF      Range end (inclusive). Default: HEAD.
  MERGE_DROPS_GLOBS         Space-separated git pathspecs whose added lines
                            are checked (default: '*.md *.qmd').
  MERGE_DROPS_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  MERGE_DROPS_MIN_LENGTH    Minimum normalised line length, inclusive
                            (default: 20).
  MERGE_DROPS_SIMILARITY    Word-level similarity, 0 to 1, at or above which
                            a line of M's copy of the same file counts as a
                            rewording of the missing line (default: 0.6;
                            1 => exact matches only).
  MERGE_DROPS_FAIL          "true" => exit 1 when a drop is found; default
                            "false" => report only.
"""

import argparse
import difflib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, FrozenSet, List, NamedTuple, Optional, Sequence, Set, Tuple, Union

_DEFAULT_GLOBS = "*.md *.qmd"
_DEFAULT_MIN_LENGTH = 20
_DEFAULT_FAIL = False
_DEFAULT_SIMILARITY = 0.6

# Blobs larger than this are not read when searching M's tree for moved
# content: a multi-megabyte file is data or generated output, not prose a
# paragraph would have moved into.
_MAX_BLOB_BYTES = 2_000_000

# How many dropped lines to print per file before summarising the rest.
_MAX_LINES_SHOWN_PER_FILE = 15

_NULL_SHA = re.compile(r"^0+$")


class Drop(NamedTuple):
    """One file's worth of lines a merge dropped from one of its parents."""

    merge: str
    subject: str
    parent_index: int  # 1-based, as in `git show M^2`
    parent: str
    path: str
    lines: List[str]


# ── git helpers ─────────────────────────────────────────────────────────────

def _git(args: Sequence[str], cwd: Optional[str] = None) -> Optional[str]:
    try:
        return subprocess.run(
            ["git", "-c", "core.quotepath=off", *args],
            capture_output=True, check=True, cwd=cwd,
            encoding="utf-8", errors="replace",
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def normalise(line: str) -> str:
    """Collapse every whitespace run to one space and trim both ends."""
    return " ".join(line.split())


# ── path filtering ──────────────────────────────────────────────────────────

def _glob_to_regex(pat: str) -> "re.Pattern[str]":
    """Translate a path glob to an anchored regex; supports ``**``, ``*``, ``?``."""
    i, n, out = 0, len(pat), []
    while i < n:
        c = pat[i]
        if c == "*":
            if pat[i:i + 2] == "**":
                i += 2
                if pat[i:i + 1] == "/":
                    out.append("(?:.*/)?")
                    i += 1
                else:
                    out.append(".*")
            else:
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def compile_ignores(patterns: List[str]) -> List["re.Pattern[str]"]:
    compiled = []
    for pat in patterns:
        compiled.append(_glob_to_regex(pat))
        if "*" not in pat and "?" not in pat:
            compiled.append(_glob_to_regex(pat.rstrip("/") + "/**"))
    return compiled


def _ignored(rel: str, ignores: List["re.Pattern[str]"]) -> bool:
    return any(r.match(rel) for r in ignores)


# ── diff parsing ────────────────────────────────────────────────────────────

def parse_added_lines(diff: str) -> Dict[str, List[str]]:
    """Map each post-image path in a ``git diff`` to the lines it adds.

    The ``+++`` header is honoured only before a file's first hunk, so an
    added content line that itself starts with ``++`` plus a space is never
    mistaken for a new file header.
    """
    added: Dict[str, List[str]] = {}
    path: Optional[str] = None
    in_header = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            in_header, path = True, None
            continue
        if in_header:
            if line.startswith("+++ "):
                target = line[4:]
                path = None if target == "/dev/null" else target[2:] if target.startswith("b/") else target
            elif line.startswith("@@"):
                in_header = False
            continue
        if path is not None and line.startswith("+"):
            added.setdefault(path, []).append(line[1:])
    return added


# ── the check ───────────────────────────────────────────────────────────────

def unbullet_line(line: str) -> str:
    """Strip line-leading markdown list item markers (-, *, +, 1.)."""
    return re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", line).strip()


def _unbullet_text(text: str) -> str:
    """Flatten text after stripping line-leading markdown list item markers."""
    stripped = [re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", line) for line in text.splitlines()]
    return " ".join(" ".join(stripped).split())


class _Blob(NamedTuple):
    lines: FrozenSet[str]  # long-enough normalised lines, for rewording checks
    flat: str              # the whole text with every whitespace run collapsed
    flat_unbulleted: str   # whole text with line-leading list markers stripped


_EMPTY_BLOB = _Blob(frozenset(), "", "")


class _TreeIndex:
    """Normalised blob contents, cached by blob SHA across merges."""

    def __init__(self, cwd: Optional[str], min_length: int):
        self._cwd = cwd
        self._min_length = min_length
        self._blobs: Dict[str, _Blob] = {}
        self._tree_key: Optional[str] = None
        self._tree_flat: Tuple[str, str] = ("", "")

    def blob(self, sha: str) -> _Blob:
        if sha not in self._blobs:
            text = _git(["cat-file", "blob", sha], cwd=self._cwd)
            if text is None or "\0" in text[:8000]:
                self._blobs[sha] = _EMPTY_BLOB
            else:
                lines = {n for n in map(normalise, text.splitlines()) if len(n) >= self._min_length}
                self._blobs[sha] = _Blob(frozenset(lines), normalise(text), _unbullet_text(text))
        return self._blobs[sha]

    def at_path(self, commit: str, path: str) -> _Blob:
        out = _git(["rev-parse", "--verify", "--quiet", f"{commit}:{path}"], cwd=self._cwd)
        return self.blob(out.strip()) if out else _EMPTY_BLOB

    def tree_flat(self, commit: str) -> Tuple[str, str]:
        """Every text blob in ``commit``'s tree, flattened, one per line.

        Returns ``(flat, flat_unbulleted)``. Only the latest tree is kept:
        consecutive lookups are for the same merge, and holding every merge's
        tree would grow without bound.
        """
        if self._tree_key != commit:
            listing = _git(["ls-tree", "-r", "-l", "-z", commit], cwd=self._cwd) or ""
            flats: List[str] = []
            unbulleted_flats: List[str] = []
            for entry in listing.split("\0"):
                meta = entry.partition("\t")[0].split()
                if len(meta) < 4 or meta[1] != "blob":
                    continue
                if not meta[3].isdigit() or int(meta[3]) > _MAX_BLOB_BYTES:
                    continue
                b = self.blob(meta[2])
                flats.append(b.flat)
                unbulleted_flats.append(b.flat_unbulleted)
            self._tree_key = commit
            self._tree_flat = ("\n".join(flats), "\n".join(unbulleted_flats))
        return self._tree_flat


def has_near_twin(line: str, others: Union[Set[str], FrozenSet[str]], threshold: float) -> bool:
    """True when some line in ``others`` is a rewording of ``line``.

    Compared word by word, so a changed number or link target costs one token
    rather than a character run. ``threshold >= 1`` disables the test.
    """
    if threshold >= 1:
        return False
    words = line.split()
    matcher = difflib.SequenceMatcher(autojunk=False)
    matcher.set_seq2(words)
    for other in others:
        matcher.set_seq1(other.split())
        if (matcher.real_quick_ratio() >= threshold
                and matcher.quick_ratio() >= threshold
                and matcher.ratio() >= threshold):
            return True
    return False


def list_merges(base: str, head: str, cwd: Optional[str] = None) -> Optional[List[List[str]]]:
    """``[[merge, parent1, parent2, ...], ...]`` for merges in base..head, oldest first."""
    out = _git(["rev-list", "--reverse", "--merges", "--parents", f"{base}..{head}"], cwd=cwd)
    if out is None:
        return None
    return [line.split() for line in out.splitlines() if line.strip()]


def check_merge(
    shas: List[str],
    globs: List[str],
    ignores: List["re.Pattern[str]"],
    min_length: int,
    index: _TreeIndex,
    cwd: Optional[str] = None,
    similarity: float = _DEFAULT_SIMILARITY,
) -> Optional[List[Drop]]:
    """Return what merge ``shas[0]`` dropped from each parent, or None if unreadable."""
    merge, parents = shas[0], shas[1:]
    base_out = _git(["merge-base", "--octopus", *parents], cwd=cwd)
    if not base_out or not base_out.strip():
        return None
    base = base_out.strip()
    subject = (_git(["log", "-1", "--format=%s", merge], cwd=cwd) or "").strip()

    drops: List[Drop] = []
    resolution_cache: Dict[str, Set[str]] = {}
    for i, parent in enumerate(parents, start=1):
        diff = _git(
            ["diff", "--no-color", "--no-ext-diff", "-U0", "-M", base, parent, "--", *globs],
            cwd=cwd,
        )
        if diff is None:
            return None
        for path, lines in parse_added_lines(diff).items():
            if _ignored(path, ignores):
                continue
            candidates: List[str] = []
            seen: Set[str] = set()
            for raw in lines:
                norm = normalise(raw)
                if len(norm) >= min_length and norm not in seen:
                    seen.add(norm)
                    candidates.append(norm)
            if not candidates:
                continue
            same_file = index.at_path(merge, path)
            missing = [c for c in candidates
                       if c not in same_file.flat
                       and unbullet_line(c) not in same_file.flat_unbulleted]
            if not missing:
                continue
            anywhere, anywhere_unbulleted = index.tree_flat(merge)
            if path not in resolution_cache:
                parent_lines: Set[str] = set()
                for p in parents:
                    parent_lines.update(index.at_path(p, path).lines)
                resolution_cache[path] = same_file.lines - parent_lines
            resolution_lines = resolution_cache[path]
            missing = [c for c in missing
                       if c not in anywhere
                       and unbullet_line(c) not in anywhere_unbulleted
                       and not has_near_twin(c, resolution_lines, similarity)]
            if missing:
                drops.append(Drop(merge, subject, i, parent, path, missing))
    return drops


def find_drops(
    base: str,
    head: str,
    globs: List[str],
    ignores: List["re.Pattern[str]"],
    min_length: int,
    cwd: Optional[str] = None,
    similarity: float = _DEFAULT_SIMILARITY,
):
    """Return ``(drops, merges_examined, unreadable_merges)``, or None to skip."""
    merges = list_merges(base, head, cwd=cwd)
    if merges is None:
        return None
    index = _TreeIndex(cwd, min_length)
    drops: List[Drop] = []
    unreadable: List[str] = []
    for shas in merges:
        if len(shas) < 3:
            continue
        found = check_merge(shas, globs, ignores, min_length, index, cwd=cwd,
                            similarity=similarity)
        if found is None:
            unreadable.append(shas[0])
        else:
            drops.extend(found)
    return drops, len(merges), unreadable


# ── reporting ───────────────────────────────────────────────────────────────

def _md_escape(text: str) -> str:
    return text.replace("`", "'")


def render_report(drops: List[Drop], merges_examined: int, base: str, head: str) -> str:
    total = sum(len(d.lines) for d in drops)
    merges_hit = len({d.merge for d in drops})
    out = [
        "## Content dropped by merge commits",
        "",
        f"Examined {merges_examined} merge commit(s) in `{base}..{head}`.",
    ]
    if not drops:
        out.append("No merge dropped a line either side had added.")
        return "\n".join(out) + "\n"
    out += [
        f"**{merges_hit} merge(s) dropped {total} line(s)** that one side added "
        "since the merge base and that appear nowhere in the merge's tree.",
        "",
        "This is what resolving a conflict by keeping one side of a whole file "
        "looks like. Check each file below: restore what was lost, or confirm "
        "the other side deliberately superseded it.",
    ]
    current = None
    for d in drops:
        if d.merge != current:
            current = d.merge
            out += ["", f"### `{d.merge[:12]}` {_md_escape(d.subject)}"]
        out += ["", f"From parent {d.parent_index} (`{d.parent[:12]}`), "
                    f"`{d.path}`: {len(d.lines)} line(s)", "", "```text"]
        for line in d.lines[:_MAX_LINES_SHOWN_PER_FILE]:
            out.append(line.replace("```", "'''"))
        if len(d.lines) > _MAX_LINES_SHOWN_PER_FILE:
            out.append(f"... and {len(d.lines) - _MAX_LINES_SHOWN_PER_FILE} more")
        out.append("```")
    return "\n".join(out) + "\n"


def _write_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)


# ── configuration ───────────────────────────────────────────────────────────

def _split_list(value: str) -> List[str]:
    return [tok.strip() for tok in re.split(r"[,\n]", value or "") if tok.strip()]


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw not in ("true", "false"):
        print(f"::warning::{name}={raw!r} is not 'true' or 'false'; using default ({default}).")
        return default
    return raw == "true"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        print(f"::warning::{name}={raw!r} is not an integer; using {default} instead.")
        return default
    if value < 1:
        print(f"::warning::{name}={raw!r} is below 1; using {default} instead.")
        return default
    return value


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        value = -1.0
    if not 0 <= value <= 1:
        print(f"::warning::{name}={raw!r} is not a number from 0 to 1; using {default} instead.")
        return default
    return value


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    parser.add_argument("--base", default=os.environ.get("MERGE_DROPS_BASE_REF", ""))
    parser.add_argument("--head", default=os.environ.get("MERGE_DROPS_HEAD_REF", "") or "HEAD")
    parser.add_argument("--globs", default=os.environ.get("MERGE_DROPS_GLOBS", "") or _DEFAULT_GLOBS)
    parser.add_argument("--paths-ignore", default=os.environ.get("MERGE_DROPS_PATHS_IGNORE", ""))
    parser.add_argument("--min-length", type=int,
                        default=_env_int("MERGE_DROPS_MIN_LENGTH", _DEFAULT_MIN_LENGTH))
    parser.add_argument("--similarity", type=float,
                        default=_env_float("MERGE_DROPS_SIMILARITY", _DEFAULT_SIMILARITY))
    parser.add_argument("--fail", action=argparse.BooleanOptionalAction,
                        default=_env_flag("MERGE_DROPS_FAIL", _DEFAULT_FAIL))
    parser.add_argument("-C", dest="cwd", default=None, help="Repository to run in.")
    args = parser.parse_args(argv)

    base = args.base.strip()
    if not base or _NULL_SHA.match(base):
        print("::warning::Skipping the merge-drops check: no base ref to start the range from.")
        return 0
    globs = args.globs.split() or _DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(args.paths_ignore))
    min_length = max(1, args.min_length)

    result = find_drops(base, args.head, globs, ignores, min_length, cwd=args.cwd,
                        similarity=args.similarity)
    if result is None:
        print(f"::warning::Skipping the merge-drops check: could not list merges in "
              f"'{base}..{args.head}' (shallow clone, or an unknown ref?). "
              f"Check out with fetch-depth: 0.")
        return 0
    drops, merges_examined, unreadable = result
    for sha in unreadable:
        print(f"::warning::Could not examine merge {sha[:12]} (no merge base found, "
              f"or a parent is missing from this clone); it was skipped.")

    report = render_report(drops, merges_examined, base, args.head)
    print(report)
    _write_summary(report)

    if not drops:
        return 0
    severity = "error" if args.fail else "warning"
    by_merge: Dict[str, List[Drop]] = {}
    for d in drops:
        by_merge.setdefault(d.merge, []).append(d)
    for merge, ds in by_merge.items():
        files = ", ".join(sorted({d.path for d in ds}))
        count = sum(len(d.lines) for d in ds)
        print(f"::{severity} title=Merge dropped content::Merge {merge[:12]} "
              f"({ds[0].subject}) dropped {count} line(s) one side added, in: {files}. "
              f"See the job summary.")
    return 1 if args.fail else 0


if __name__ == "__main__":
    sys.exit(main())
