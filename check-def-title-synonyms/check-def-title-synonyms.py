#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a definition-div title that lists its synonyms the wrong way.

The lab's rule (Ezra, 2026-10-23; Morrison-Lab/psw#338): the title of a
``#def-`` div names a term and its synonyms as a comma-separated list with the
primary term first, as in "Logistic function, sigmoid, expit". Not
"Logistic function (also called the sigmoid or expit)", and not
"Level set (level curve, contour)".

A title is the first heading line inside a ``#def-`` div, or its ``title=``
attribute. It is flagged when it is on a line the diff adds and holds a
parenthesis, "also called", "also known as", "a.k.a.", "aka" or "or simply".
Math (``$...$``) and a parenthetical that contains math are ignored, because
"Almost everywhere ($f = g$ a.e.)" gives notation, not a synonym.

Diff-scoped like check-one-div-per-subfile: only an added line is reported, an
untouched title keeps its form, and with no base ref the check skips rather
than scanning the whole tree. ``DTS_WHOLE_TREE=true`` measures a corpus.

Configuration (environment variables, set by the composite action):
  DTS_BASE_REF    Git ref/SHA to diff against. Empty and not whole-tree => skip.
  DTS_GLOBS       Space-separated git pathspecs (default: '*.qmd').
  DTS_FAIL        "true" => exit 1 on a finding; default "false" => warnings.
  DTS_WHOLE_TREE  "true" => scan every tracked matching file in full.
"""

import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Set, Tuple

DEFAULT_GLOBS = "*.qmd"
ADVICE = ('write the title as a comma list with the primary term first, '
          'for example "Logistic function, sigmoid, expit"')

DEF_OPEN_RE = re.compile(r"^ {0,3}:{3,}\s*\{[^}]*#def-[^}]*\}")
HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
TITLE_ATTR_RE = re.compile(r"""title\s*=\s*(?:"([^"]*)"|'([^']*)')""")
MATH_RE = re.compile(r"\$[^$]*\$")
BAD_RE = re.compile(r"[()]|\balso (?:called|known as)\b|\ba\.k\.a\.|\baka\b|\bor simply\b",
                    re.IGNORECASE)
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


MATH_PAREN_RE = re.compile(r"\([^()]*\$[^()]*\)")


def bad_title(title: str) -> bool:
    plain = MATH_RE.sub("", MATH_PAREN_RE.sub("", title))
    return bool(BAD_RE.search(plain))


def def_titles(lines: List[str]) -> List[Tuple[int, str]]:
    """``(line number, title)`` of each ``#def-`` div's title."""
    found: List[Tuple[int, str]] = []
    waiting = False
    for idx, raw in enumerate(lines):
        if DEF_OPEN_RE.match(raw):
            attr = TITLE_ATTR_RE.search(raw)
            if attr:
                found.append((idx + 1, attr.group(1) or attr.group(2)))
                waiting = False
            else:
                waiting = True
            continue
        if waiting and raw.strip():
            heading = HEADING_RE.match(raw)
            if heading:
                found.append((idx + 1, heading.group(1)))
            waiting = False
    return found


def added_lines(diff: str) -> Dict[str, Set[int]]:
    """Added line numbers per path from ``git diff -U0`` output."""
    added: Dict[str, Set[int]] = {}
    path: Optional[str] = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].rstrip("\t")
            path = None if target == "/dev/null" else target.removeprefix("b/")
            if path is not None:
                added.setdefault(path, set())
            continue
        m = HUNK_RE.match(line)
        if m and path is not None:
            start = int(m.group(1))
            count = 1 if m.group(2) is None else int(m.group(2))
            added[path].update(range(start, start + count))
    return added


def _git(args: List[str]) -> Optional[str]:
    res = subprocess.run(["git", "-c", "core.quotepath=false", *args],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", errors="replace")
    return res.stdout if res.returncode == 0 else None


def wanted_lines(base_ref: str, globs: List[str], whole_tree: bool
                 ) -> Optional[Dict[str, Optional[Set[int]]]]:
    """Files to scan, each with its added lines (None = every line)."""
    if whole_tree:
        out = _git(["ls-files", "--", *globs])
        return None if out is None else {p: None for p in out.splitlines() if p}
    if not base_ref:
        return None
    base = _git(["merge-base", base_ref, "HEAD"])
    if not base or not base.strip():
        return None
    diff = _git(["diff", "-U0", "--no-color", "--no-ext-diff", base.strip(),
                 "--", *globs])
    return None if diff is None else dict(added_lines(diff))


def main() -> int:
    base_ref = os.environ.get("DTS_BASE_REF", "").strip()
    globs = os.environ.get("DTS_GLOBS", DEFAULT_GLOBS).split() or [DEFAULT_GLOBS]
    fail = os.environ.get("DTS_FAIL", "").strip().lower() in ("1", "true", "yes", "on")
    whole = os.environ.get("DTS_WHOLE_TREE", "").strip().lower() in ("1", "true", "yes", "on")
    wanted = wanted_lines(base_ref, globs, whole)
    if wanted is None:
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the definition-title synonym check for this run "
              f"({'could not diff against ' + repr(base_ref) if base_ref else 'no base-ref given'}).")
        return 0
    severity = "error" if fail else "warning"
    titles = findings = 0
    for rel in sorted(wanted):
        try:
            with open(rel, encoding="utf-8", errors="replace") as handle:
                lines = handle.read().split("\n")
        except OSError:
            continue
        keep = wanted[rel]
        for number, title in def_titles(lines):
            titles += 1
            if (keep is None or number in keep) and bad_title(title):
                findings += 1
                print(f"::{severity} file={rel},line={number}::Definition title "
                      f"'{title}' lists synonyms with parentheses or 'also called'. "
                      f"Fix: {ADVICE}")
    print(f"Examined {titles} definition title(s) in {len(wanted)} file(s); "
          f"{findings} flagged.")
    return 1 if findings and fail else 0


if __name__ == "__main__":
    sys.exit(main())
