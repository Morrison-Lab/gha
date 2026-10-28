#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a solution paragraph that opens with a bare "Yes." or "No.".

The lab's rule (Ezra, 2026-10-28; Morrison-Lab/psw teaching chapter): an
answer to a yes-or-no question says what it means in the question's own
terms, as in "No: it's not possible that the advanced network has a test
error of 0.25", not a bare "No." that leaves the reader to guess what is
denied.

What is flagged: inside a solution div (id ``sol-...`` or class ``.sol``,
``.solution`` or ``.answer``), a paragraph or list item whose text begins
with Yes or No, bare or bolded or italic, followed by a period or
exclamation mark, or by nothing. "No: it's not possible that ...", "No, the
test error ..." and "No other notes" are not flagged. Code fences and HTML comments are skipped.

Diff-scoped like check-def-title-synonyms: only an added line is reported, an
untouched answer keeps its form, and with no base ref the check skips rather
than scanning the whole tree. ``BYN_WHOLE_TREE=true`` measures a corpus.

Configuration (environment variables, set by the composite action):
  BYN_BASE_REF    Git ref/SHA to diff against. Empty and not whole-tree => skip.
  BYN_GLOBS       Space-separated git pathspecs (default: '*.qmd').
  BYN_FAIL        "false" => warnings only; default "true" => exit 1.
  BYN_WHOLE_TREE  "true" => scan every tracked matching file in full.
"""

import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Set, Tuple

DEFAULT_GLOBS = "*.qmd"
ADVICE = ('follow it with what the answer means, for example '
          '"No: it is not possible that the advanced network has a test error of 0.25."')

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
SOL_RE = re.compile(r"#sol-|\.(?:sol|solution|answer)\b")
# After optional quote, list marker and emphasis: Yes/No then end or punctuation.
BARE_RE = re.compile(
    r"^[ \t]*(?:>\s*)*(?:(?:[-*+]|\d{1,2}[.)]|\(?[a-z][.)]|\([a-z]\))\s+)?"
    r"(?:\*\*|__|\*|_)*(?:Yes|No)(?:\*\*|__|\*|_)*(?:[.!](?:\*\*|__|\*|_)*(?:\s|$)|$)"
)
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def bare_answers(lines: List[str]) -> List[Tuple[int, str]]:
    """``(line number, text)`` of each bare Yes/No opener inside a solution div."""
    found: List[Tuple[int, str]] = []
    fence: Optional[str] = None
    in_comment = False
    depth = 0
    sol_depth: Optional[int] = None
    for idx, raw in enumerate(lines):
        if in_comment:
            in_comment = "-->" not in raw
            continue
        if raw.lstrip().startswith("<!--") and "-->" not in raw:
            in_comment = True
            continue
        fm = FENCE_RE.match(raw)
        if fence is not None:
            if fm and fm.group(1)[0] == fence:
                fence = None
            continue
        if fm:
            fence = fm.group(1)[0]
            continue
        dm = DIV_RE.match(raw)
        if dm:
            if dm.group(2):
                if sol_depth is None and SOL_RE.search(dm.group(2)):
                    sol_depth = depth
                depth += 1
            elif depth > 0:
                depth -= 1
                if sol_depth is not None and depth == sol_depth:
                    sol_depth = None
            continue
        if sol_depth is not None and BARE_RE.match(raw):
            found.append((idx + 1, raw.strip()))
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


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return default if not value else value in ("1", "true", "yes", "on")


def main() -> int:
    base_ref = os.environ.get("BYN_BASE_REF", "").strip()
    globs = os.environ.get("BYN_GLOBS", DEFAULT_GLOBS).split() or [DEFAULT_GLOBS]
    fail = _flag("BYN_FAIL", True)
    whole = _flag("BYN_WHOLE_TREE", False)
    wanted = wanted_lines(base_ref, globs, whole)
    if wanted is None:
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the bare yes/no check for this run "
              f"({'could not diff against ' + repr(base_ref) if base_ref else 'no base-ref given'}).")
        return 0
    severity = "error" if fail else "warning"
    findings = 0
    for rel in sorted(wanted):
        try:
            with open(rel, encoding="utf-8", errors="replace") as handle:
                lines = handle.read().split("\n")
        except OSError:
            continue
        keep = wanted[rel]
        for number, text in bare_answers(lines):
            if keep is None or number in keep:
                findings += 1
                print(f"::{severity} file={rel},line={number}::Solution opens with "
                      f"a bare yes or no ('{text[:40]}'). Fix: {ADVICE}")
    print(f"Examined {len(wanted)} file(s); {findings} bare yes/no answer(s) flagged.")
    return 1 if findings and fail else 0


if __name__ == "__main__":
    sys.exit(main())
