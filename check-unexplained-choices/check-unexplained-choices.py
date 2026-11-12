#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag an analysis choice in code that the prose around it never explains.

The lab's rule (Ezra, 2026-11-03; Morrison-Lab/ai-config#4905): every time an
author makes an arbitrary analysis choice, such as binning a variable, the
prose explains the decision in detail. Example: lds `fig-logistic-regression`
cut age into three-year bins and said nothing about why (lds#1725).

Whether an explanation is good is a judgment no script can make. This check is
a prompt: it flags a code line that makes a binning choice (``cut()``,
``breaks =``, ``bins =``, ``binwidth =``) in a
unit of the page whose prose holds no reason word.

The unit is the outermost div around the code (a figure, example or exercise),
or, outside any div, the text from the previous heading to the next one.

What is not flagged:

- a unit whose prose, outside code fences, display math and HTML comments,
  holds a reason word (``because``, ``chose``, ``choice``, ``compromise``,
  ``rather than``, ``alternative``, ``arbitrary``, ...);
- a code line starting with ``#`` (a comment or a ``#|`` chunk option);
- a line carrying ``<!-- check-unexplained-choices: allow -->``.

Only binning is recognized, because a choice that needs no reason (a seed in a
plain simulation) would make a failing check noisy.

Design notes, in the model of ``check-unexplained-contrasts``:

- **Diff-scoped by default.** Only an added line is reported. The whole file
  is parsed, since the explaining prose may sit far from the changed line.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``UAC_WHOLE_TREE=true`` scans the
  whole tree, which measures how many existing choices go unexplained.
- **Failing by default** (``UAC_FAIL`` defaults to true): an agent ignores a
  warning, so the pattern list is kept narrow to binning.

Configuration (environment variables, set by the composite action):
  UAC_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  UAC_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  UAC_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  UAC_FAIL          "true" => error annotations and a failing exit
                    (the default); "false" => warnings only.
  UAC_WHOLE_TREE    "true" => scan every tracked matching file in full.
"""

import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "check-common"))
import diffscope  # noqa: E402
import mdmask  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = True
ALLOW_MARKER = "check-unexplained-choices: allow"

ADVICE = (
    "explain the choice in the prose next to it: what was chosen, what the "
    "alternatives were, and why this one, with numbers from the data where "
    "they bear on it; remove the choice if there is no reason; or add "
    "<!-- check-unexplained-choices: allow --> if it is not an analysis choice"
)

CHOICE_RE = re.compile(
    r"(\bcut\s*\("
    r"|\bcut_(?:number|interval|width)\s*\("
    r"|\bpd\.(?:cut|qcut)\s*\("
    r"|\b(?:breaks|bins|binwidth|nbins|n_bins)\s*=)"
)
REASON_RE = re.compile(
    r"\b(?:because|chose|chosen|choice|choose|so that|compromise|rather than|"
    r"trade-?off|in order to|why|reason|arbitrary|alternatives?|picked|"
    r"reproducib\w+)\b",
    re.IGNORECASE,
)

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
HEADING_RE = re.compile(r"^#{1,6}\s")


class Finding(NamedTuple):
    line: int
    phrase: str


class _Unit:
    """The text a choice is read against: its hits and whether prose explains."""

    def __init__(self) -> None:
        self.hits: List[Finding] = []
        self.explained = False

    def flush(self) -> List[Finding]:
        found = [] if self.explained else self.hits
        self.hits, self.explained = [], False
        return found


def strip_comment(raw: str, in_comment: bool) -> Tuple[str, bool]:
    """Drop HTML comment text from one line; say whether one stays open."""
    out, i = [], 0
    while i < len(raw):
        if in_comment:
            end = raw.find("-->", i)
            if end < 0:
                return "".join(out), True
            i, in_comment = end + 3, False
        else:
            start = raw.find("<!--", i)
            if start < 0:
                out.append(raw[i:])
                break
            out.append(raw[i:start])
            i, in_comment = start + 4, True
    return "".join(out), in_comment


def scan_choices(lines: List[str]) -> List[Finding]:
    """Choices in code whose unit (outer div, or section) has no reason prose."""
    findings: List[Finding] = []
    section = _Unit()
    depth = 0
    outer = _Unit()
    fence: Optional[Tuple[str, int]] = None
    in_math = in_comment = False
    for idx, original in enumerate(lines):
        raw = original
        if fence is None:
            raw, in_comment = strip_comment(raw, in_comment)
        unit = outer if depth > 0 else section
        m = FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
                continue
            code = raw.strip()
            if code and not code.startswith("#") and ALLOW_MARKER not in original:
                hit = CHOICE_RE.search(code)
                if hit:
                    unit.hits.append(Finding(idx + 1, hit.group(1).strip("( =")))
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        if raw.count("$$") % 2 == 1:
            in_math = not in_math
            continue
        if in_math:
            continue
        dm = DIV_RE.match(raw)
        if dm:
            if dm.group(2):
                if depth == 0:
                    findings.extend(section.flush())
                depth += 1
            elif depth > 0:
                depth -= 1
                if depth == 0:
                    findings.extend(outer.flush())
            continue
        if depth == 0 and HEADING_RE.match(raw):
            findings.extend(section.flush())
            continue
        if REASON_RE.search(mdmask.CODE_SPAN_RE.sub(" ", raw)):
            unit.explained = True
    findings.extend(outer.flush())
    findings.extend(section.flush())
    return sorted(findings)


def format_message(phrase: str) -> str:
    return (f"Analysis choice (`{phrase}`) with no reason in the prose of its "
            f"figure, example or section. Fix: {ADVICE}")


# -- Git plumbing ------------------------------------------------------------

# The diff-scoping helpers live in check-common/diffscope.py (gha#1856).


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
    files: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    """Scan files with an added line since ``base_ref``, or all when whole-tree."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        paths = diffscope.git_paths(["ls-files", "--", *globs])
        if paths is None:
            return Report([], 0, True)
        for rel in paths:
            if rel and not diffscope.ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, True)
        base = diffscope.run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, True)
        diff = diffscope.run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                                  base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, True)
        added, deleted = diffscope.parse_diff(diff)
        for rel, numbered in added.items():
            if diffscope.ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if text.strip() and text not in deleted}

    findings: List[Tuple[str, Finding]] = []
    files = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        for found in scan_choices(content):
            if keep is None or found.line in keep:
                findings.append((rel, found))
    return Report(findings, files, False)


def main() -> int:
    base_ref = os.environ.get("UAC_BASE_REF", "").strip()
    globs = os.environ.get("UAC_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignore_list = diffscope.split_list(os.environ.get("UAC_PATHS_IGNORE", ""))
    ignores = diffscope.compile_ignores(ignore_list)
    fail = diffscope.env_flag("UAC_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("UAC_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the unexplained-choices check for this run "
              f"({reason}; not falling back to a whole-tree scan, which would "
              f"reflag every choice the corpus already carries).")
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.files} file(s) (scope: {scope}).")
    severity = "error" if fail else "warning"
    for rel, found in report.findings:
        print(f"::{severity} file={rel},line={found.line}::{format_message(found.phrase)}")
    if not report.findings:
        print("No unexplained analysis choice found.")
        return 0
    print(f"\n{len(report.findings)} unexplained analysis choice(s).")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
