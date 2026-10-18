#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a subfile that holds more than one top-level div.

The lab's rule (Ezra, 2026-10-18; Morrison-Lab/gha#1092): new and revised
content gets one div per subfile, a solution in its own ``_sol`` file
included. A subfile that is not otherwise touched keeps its present layout.

What is flagged: a subfile, that is, a ``.qmd`` file whose name starts with
``_`` and which sits under a ``_subfiles`` directory, that has more than one
top-level fenced div, when the diff adds at least one line to it. A touched
subfile counts as revised, so a one-line fix to a file that still holds an
exercise and its solution is reported too. The finding sits on the opening
line of the second top-level div.

What is not counted:

- a div nested inside another div (only top-level divs count);
- a top-level div whose id starts with ``rem-source-`` (a source remark that
  belongs right after the item it credits);
- fences inside code blocks;
- a subfile with one div, or none (a figure chunk, a paragraph).

Design notes, in the model of ``check-wikipedia-further-reading``:

- **Diff-scoped by default.** Only a subfile with a line *added* since
  ``ODS_BASE_REF`` is reported. The whole file is parsed (a div opens far
  above the line that changed). An added line whose exact text was also
  deleted in the same diff is treated as moved, not new, and a blank added
  line is not content.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed (a shallow clone), the check skips with a warning.
  ``ODS_WHOLE_TREE=true`` asks for the whole tree explicitly, which measures
  how many existing subfiles hold several divs.
- **Warn-only by default** (``ODS_FAIL`` defaults to false): the lab's
  subfile layout predates the rule, and a rename sweep is separate work.
- **The search space is reported**: files, lines and divs examined.

Configuration (environment variables, set by the composite action):
  ODS_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  ODS_GLOBS         Space-separated git pathspecs
                    (default: '*_subfiles/*.qmd').
  ODS_PATHS_IGNORE  Comma/newline-separated glob patterns (relative paths) to
                    skip. Supports ``*``, ``?`` and recursive ``**``.
  ODS_FAIL          "true" => exit 1 on a finding; default "false" => warning
                    annotations only.
  ODS_WHOLE_TREE    "true" => scan every tracked matching file in full.
"""

import os
import re
import subprocess
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*_subfiles/*.qmd"
_DEFAULT_FAIL = False

ADVICE = (
    "give each div its own subfile named _<stem>_<type>.qmd "
    "(_def, _exr, _sol, _thm, _exm, _fig, _rem) and include each from the "
    "chapter"
)

# -- Parsing -----------------------------------------------------------------

FENCE_RE = re.compile(r"^[ \t>]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
SOURCE_ID_RE = re.compile(r"#rem-source-")


class Div(NamedTuple):
    line: int
    attrs: str


def is_subfile(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    return (parts[-1].startswith("_") and parts[-1].endswith(".qmd")
            and "_subfiles" in parts[:-1])


def top_level_divs(lines: List[str]) -> List[Div]:
    """Top-level fenced divs outside code fences, minus source remarks."""
    fence: Optional[Tuple[str, int]] = None
    depth = 0
    found: List[Div] = []
    for idx, raw in enumerate(lines):
        m = FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        if m:
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        dm = DIV_RE.match(raw)
        if not dm:
            continue
        attrs = dm.group(2)
        if attrs:
            if depth == 0 and not SOURCE_ID_RE.search(attrs):
                found.append(Div(idx + 1, attrs))
            depth += 1
        elif depth > 0:
            depth -= 1
    return found


def scan_file(lines: List[str], path: str = "") -> Tuple[List[Div], int]:
    """Divs after the first one in a subfile, and the divs seen."""
    if path and not is_subfile(path):
        return [], 0
    divs = top_level_divs(lines)
    return divs[1:], len(divs)


# -- Messages ----------------------------------------------------------------

def format_message(count: int) -> str:
    return (f"Subfile holds {count} top-level divs; new and revised content "
            f"gets one div per subfile. Fix: {ADVICE}")


# -- Git plumbing ------------------------------------------------------------

def _run_git(args: List[str]) -> Optional[str]:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    return res.stdout if res.returncode == 0 else None


_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_diff(diff: str) -> Tuple[Dict[str, Dict[int, str]], Set[str]]:
    """Added ``{path: {line_number: text}}`` and the set of deleted texts.

    Hunk header counts decide where a hunk ends, so an added line that begins
    with two plus signs is never mistaken for a ``+++`` file header.
    """
    added: Dict[str, Dict[int, str]] = {}
    deleted: Set[str] = set()
    path: Optional[str] = None
    old_left = new_left = new_line = 0
    for line in diff.splitlines():
        if old_left > 0 or new_left > 0:
            if line.startswith("+"):
                if path is not None:
                    added[path][new_line] = line[1:]
                new_line += 1
                new_left -= 1
            elif line.startswith("-"):
                deleted.add(line[1:])
                old_left -= 1
            continue
        if line.startswith("+++ "):
            target = line[4:].rstrip("\t")
            path = None if target == "/dev/null" else target[2:] if target.startswith("b/") else target
            if path is not None:
                added.setdefault(path, {})
            continue
        m = _HUNK_RE.match(line)
        if m:
            old_left = int(m.group(1)) if m.group(1) is not None else 1
            new_line = int(m.group(2))
            new_left = int(m.group(3)) if m.group(3) is not None else 1
    return added, deleted


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


def _split_list(value: str) -> List[str]:
    return [p.strip() for p in re.split(r"[,\n]", value) if p.strip()]


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


class Report(NamedTuple):
    findings: List[Tuple[str, int, int]]  # (path, line of the 2nd div, divs)
    files: int
    lines: int
    divs: int
    skipped: bool


def _read_lines(path: str) -> Optional[List[str]]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().split("\n")
    except OSError:
        return None
    if lines and lines[-1] == "":
        lines.pop()  # the newline ending the file does not start a line
    return lines


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    """Scan subfiles with an added line since ``base_ref``, or all when whole-tree."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = _run_git(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, 0, 0, True)
        for rel in out.splitlines():
            if rel and not _ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, 0, True)
        base = _run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, 0, True)
        diff = _run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                         base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, 0, True)
        added, deleted = parse_diff(diff)
        for rel, numbered in added.items():
            if _ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if text.strip() and text not in deleted}

    findings: List[Tuple[str, int, int]] = []
    files = lines = divs = 0
    for rel in sorted(wanted):
        if not is_subfile(rel):
            continue
        content = _read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        extra, seen = scan_file(content, rel)
        divs += seen
        if extra and (keep is None or keep):
            findings.append((rel, extra[0].line, seen))
    return Report(findings, files, lines, divs, False)


def main() -> int:
    base_ref = os.environ.get("ODS_BASE_REF", "").strip()
    globs = os.environ.get("ODS_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("ODS_PATHS_IGNORE", "")))
    fail = _env_flag("ODS_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("ODS_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(
            f"::warning::Skipping the one-div-per-subfile check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every subfile the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} subfile(s), "
        f"{report.divs} top-level div(s) (scope: {scope})."
    )
    if not report.findings:
        print("No subfile holds more than one top-level div.")
        return 0

    severity = "error" if fail else "warning"
    for rel, line, count in report.findings:
        print(f"::{severity} file={rel},line={line}::{format_message(count)}")
    print(f"\n{len(report.findings)} subfile(s) hold more than one top-level div.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
