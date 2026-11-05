#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag an executed code chunk that sets ``#| code-fold: false``.

The lab's rule (Ezra, 2026-11-05; Morrison-Lab/psw teaching chapter, "Set
`code-fold` by whether the prose mentions the code"): every executed chunk is
``show`` (the prose mentions the code, so it starts open and can be folded) or
``true`` (the prose does not, so it starts hidden and can be opened).
``false`` removes the toggle and gains nothing, because ``show`` also keeps the
code and its output together.

What is flagged: a ``#| code-fold: false`` option line (also ``FALSE`` or a
quoted ``"false"``) in the option block at the top of a chunk whose fence
names an engine, such as ``{r}``, ``{python}`` or ``{julia}``. A plain fence
has no options. A ``code-fold: false`` anywhere else, such as in front matter,
is not examined.

Diff-scoped like check-bare-yes-no: only an added line is reported, an
untouched chunk keeps its option, and with no base ref the check skips rather
than scanning the whole tree. ``CCF_WHOLE_TREE=true`` measures a corpus.

Configuration (environment variables, set by the composite action):
  CCF_BASE_REF    Git ref/SHA to diff against. Empty and not whole-tree => skip.
  CCF_GLOBS       Space-separated git pathspecs (default: '*.qmd').
  CCF_FAIL        "false" => warnings only; default "true" => exit 1.
  CCF_WHOLE_TREE  "true" => scan every tracked matching file in full.
"""

import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Set, Tuple

DEFAULT_GLOBS = "*.qmd"
ADVICE = ("set `#| code-fold: show` when the prose mentions the code, "
          "or `#| code-fold: true` when it does not")

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
ENGINE_RE = re.compile(r"^\s*\{[ \t]*[A-Za-z][\w-]*[ \t,}]")
OPTION_RE = re.compile(r"^[ \t]*#\|(.*)$")
FOLD_FALSE_RE = re.compile(r"^\s*code-fold\s*:\s*[\"']?false[\"']?\s*$", re.IGNORECASE)
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def fold_false_options(lines: List[str]) -> List[Tuple[int, str]]:
    """``(line number, text)`` of each ``code-fold: false`` option in an executed chunk."""
    found: List[Tuple[int, str]] = []
    fence: Optional[str] = None
    executed = False
    in_options = False
    for idx, raw in enumerate(lines):
        fm = FENCE_RE.match(raw)
        if fence is None:
            if fm:
                fence = fm.group(1)[0]
                executed = bool(ENGINE_RE.match(fm.group(2)))
                in_options = executed
            continue
        if fm and fm.group(1)[0] == fence and not fm.group(2).strip():
            fence = None
            executed = False
            in_options = False
            continue
        if not (executed and in_options):
            continue
        om = OPTION_RE.match(raw)
        if om:
            if FOLD_FALSE_RE.match(om.group(1)):
                found.append((idx + 1, raw.strip()))
        else:
            in_options = False
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
    base_ref = os.environ.get("CCF_BASE_REF", "").strip()
    globs = os.environ.get("CCF_GLOBS", DEFAULT_GLOBS).split() or [DEFAULT_GLOBS]
    fail = _flag("CCF_FAIL", True)
    whole = _flag("CCF_WHOLE_TREE", False)
    wanted = wanted_lines(base_ref, globs, whole)
    if wanted is None:
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the code-fold check for this run "
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
        for number, text in fold_false_options(lines):
            if keep is None or number in keep:
                findings += 1
                print(f"::{severity} file={rel},line={number}::Chunk sets "
                      f"'{text[:40]}'. Fix: {ADVICE}.")
    print(f"Examined {len(wanted)} file(s); {findings} code-fold: false option(s) flagged.")
    return 1 if findings and fail else 0


if __name__ == "__main__":
    sys.exit(main())
