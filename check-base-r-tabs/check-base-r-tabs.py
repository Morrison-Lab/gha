#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a language tabset that has an "R (tidymodels)" tab and no base R tab.

The lab's rule (Morrison-Lab/psw, "Write labs for both languages and any
computer"): write the R code with tidymodels, or show tidymodels and base R
side by side. A textbook lab such as ISL's writes its R code in base R, so a
lab that adapts one keeps the book's base R code in a plain "R" tab beside the
tidymodels version (Ezra, 2026-11-17, Morrison-Lab/lds#2708: "I don't think
the original ISLR labs used tidymodels; go back and look").

What is flagged: a ``::: {.panel-tabset}`` div whose tab headings include
"R (tidymodels)" (any heading level, any case) but no base R tab. A base R tab
is a heading that reads exactly "R", "Base R", "R (base)" or "R (base R)".
Headings inside code fences and in nested divs below the tab level are
ignored. The finding is reported at the "R (tidymodels)" heading.

Diff-scoped: a tabset is reported only when the diff adds a line inside it,
so a PR that adds or edits a tidymodels-only tabset fails, and an untouched
one does not. With no base ref the check skips rather than scanning the whole
tree. ``CBR_WHOLE_TREE=true`` measures a corpus.

A tabset whose R code has no base R counterpart can opt out with
``<!-- base-r-tab: none: reason -->`` anywhere inside the tabset; the reason
is required.

Configuration (environment variables, set by the composite action):
  CBR_BASE_REF    Git ref/SHA to diff against. Empty and not whole-tree => skip.
  CBR_GLOBS       Space-separated git pathspecs (default: '*.qmd').
  CBR_FAIL        "false" => warnings only; default "true" => exit 1.
  CBR_WHOLE_TREE  "true" => scan every tracked matching file in full.
"""

import os
import re
import sys
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402
from mdmask import FENCE_RE  # noqa: E402

DEFAULT_GLOBS = "*.qmd"
ADVICE = ("add a base R tab (headed \"R\") beside the tidymodels tab, "
          "following the source lab's base R code where there is one")

DIV_OPEN_RE = re.compile(r"^[ \t]*(:{3,})[ \t]*(\S.*)$")
DIV_CLOSE_RE = re.compile(r"^[ \t]*(:{3,})[ \t]*$")
TABSET_RE = re.compile(r"(^|[\s{])\.panel-tabset([\s}]|$)")
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
TIDY_RE = re.compile(r"^R\s*\(\s*tidymodels\s*\)$", re.IGNORECASE)
BASE_RE = re.compile(r"^(R|base R|R\s*\(\s*base(\s+R)?\s*\))$", re.IGNORECASE)
OPT_OUT_RE = re.compile(r"<!--\s*base-r-tab:\s*none:\s*\S[^>]*-->")
ATTR_RE = re.compile(r"\s*\{[^}]*\}\s*$")


class Tabset:
    """One panel-tabset div: its line span and its tab headings."""

    def __init__(self, start: int):
        self.start = start
        self.end = start
        self.level: Optional[int] = None
        self.tabs: List[Tuple[int, str]] = []
        self.opted_out = False


def heading_text(raw: str) -> str:
    """Heading text without trailing ``{...}`` attributes."""
    return ATTR_RE.sub("", raw).strip()


def tabsets(lines: List[str]) -> List[Tabset]:
    """Every panel-tabset div in ``lines``, with its tab headings."""
    found: List[Tabset] = []
    # Each open div: (colon count, Tabset or None, depth inside the tabset).
    stack: List[Tuple[int, Optional[Tabset]]] = []
    fence: Optional[str] = None
    for idx, raw in enumerate(lines):
        number = idx + 1
        fm = FENCE_RE.match(raw)
        if fence is not None:
            if fm and fm.group(1)[0] == fence[0] and len(fm.group(1)) >= len(fence) \
                    and not fm.group(2).strip():
                fence = None
            continue
        if fm:
            fence = fm.group(1)
            continue
        close = DIV_CLOSE_RE.match(raw)
        if close and stack:
            _colons, tabset = stack.pop()
            if tabset is not None:
                tabset.end = number
            continue
        opened = DIV_OPEN_RE.match(raw)
        if opened:
            if TABSET_RE.search(opened.group(2)):
                tabset = Tabset(number)
                found.append(tabset)
                stack.append((len(opened.group(1)), tabset))
            else:
                stack.append((len(opened.group(1)), None))
            continue
        if not stack:
            continue
        current = stack[-1][1]
        if current is None:
            # Inside a div nested in a tabset: not a tab heading, but an
            # opt-out comment there still belongs to the enclosing tabset.
            outer = next((t for _c, t in reversed(stack) if t is not None), None)
            if outer is not None and OPT_OUT_RE.search(raw):
                outer.opted_out = True
            continue
        if OPT_OUT_RE.search(raw):
            current.opted_out = True
        hm = HEADING_RE.match(raw)
        if hm:
            level = len(hm.group(1))
            if current.level is None:
                current.level = level
            if level == current.level:
                current.tabs.append((number, heading_text(hm.group(2))))
    return found


def missing_base_r(lines: List[str]) -> List[Tuple[int, int, int]]:
    """``(tidymodels heading line, tabset start, tabset end)`` per offending tabset."""
    out: List[Tuple[int, int, int]] = []
    for tabset in tabsets(lines):
        if tabset.opted_out:
            continue
        tidy = [n for n, text in tabset.tabs if TIDY_RE.match(text)]
        has_base = any(BASE_RE.match(text) for _n, text in tabset.tabs)
        if tidy and not has_base:
            out.append((tidy[0], tabset.start, tabset.end))
    return out


def added_lines(diff: str) -> Dict[str, Set[int]]:
    """Added line numbers per path from ``git diff -U0`` output."""
    added, _deleted = diffscope.parse_diff(diff)
    return {path: set(numbered) for path, numbered in added.items()}


def wanted_lines(base_ref: str, globs: List[str], whole_tree: bool
                 ) -> Optional[Dict[str, Optional[Set[int]]]]:
    """Files to scan, each with its added lines (None = every line)."""
    if whole_tree:
        paths = diffscope.git_paths(["ls-files", "--", *globs])
        return None if paths is None else {p: None for p in paths}
    if not base_ref:
        return None
    base = diffscope.run_git(["merge-base", base_ref, "HEAD"])
    if not base or not base.strip():
        return None
    diff = diffscope.run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                              base.strip(), "--", *globs])
    return None if diff is None else added_lines(diff)


_flag = diffscope.env_flag


def main() -> int:
    base_ref = os.environ.get("CBR_BASE_REF", "").strip()
    globs = os.environ.get("CBR_GLOBS", DEFAULT_GLOBS).split() or [DEFAULT_GLOBS]
    fail = _flag("CBR_FAIL", True)
    whole = _flag("CBR_WHOLE_TREE", False)
    wanted = wanted_lines(base_ref, globs, whole)
    if wanted is None:
        if base_ref:
            level = "::warning::"
            reason = f"could not diff against {base_ref!r}"
        else:
            level = ""
            reason = "no base-ref given"
        print(f"{level}Skipping the base R tab check for this run ({reason}).")
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
        for heading, start, end in missing_base_r(lines):
            if keep is not None and not any(start <= n <= end for n in keep):
                continue
            findings += 1
            print(f"::{severity} file={rel},line={heading}::Tabset has an "
                  f"\"R (tidymodels)\" tab and no base R tab. Fix: {ADVICE}, "
                  f"or opt out with <!-- base-r-tab: none: reason -->.")
    print(f"Examined {len(wanted)} file(s); {findings} tabset(s) without a base R tab flagged.")
    return 1 if findings and fail else 0


if __name__ == "__main__":
    sys.exit(main())
