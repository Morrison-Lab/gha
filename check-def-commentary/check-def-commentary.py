#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag commentary written inside a ``#def-`` div.

The lab's rule (Ezra, 2026-10-23, sds#444 review; Morrison-Lab/gha#1180): a
definition div holds the definition, its notation and its display equation
only. Commentary, contrasts ("it is not X"), motivation and history go in a
``#rem-`` div right after it, one div per subfile. The same mistake had been
corrected before and was written again.

What is flagged: a sentence inside a ``::: {#def-...}`` div that opens with a
commentary phrase: "It is not", "This is not", "That is not", "Note that",
"Notice that", "Unlike", "Do not confuse", "Be careful", "Beware", "In
contrast", "By contrast", "Intuitively", "Informally", "Historically", "Extends" and "Generalizes"
(also after "This" or "It"), "Just as", "Similarly", "Equivalently", "In
other words", and a special-case opener such as "For $p = 1$". The
finding sits on the line that holds the sentence.

What is not counted: lines inside code fences, display math (``$$``), HTML
comments, or a div nested inside the definition (a ``#def-`` div's own lines
are the only ones read); a line carrying ``<!-- check-def-commentary: allow
-->``, for a sentence that really is part of the definition. The heuristic is
noisy by design, and the marker is its escape hatch.

Design notes, in the model of ``check-one-div-per-subfile``:

- **Diff-scoped by default.** Only an added line is reported. The whole file
  is parsed, since the div opens far above the line that changed. An added
  line whose exact text was also deleted in the diff counts as moved.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``DCM_WHOLE_TREE=true`` scans the
  whole tree, which measures how many existing definitions carry commentary.
- **Blocking by default** (``DCM_FAIL`` defaults to true): it is diff-scoped,
  so it reflags nothing the corpus already carries.

Configuration (environment variables, set by the composite action):
  DCM_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  DCM_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  DCM_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  DCM_FAIL          "false" => warning annotations only; default "true".
  DCM_WHOLE_TREE    "true" => scan every tracked matching file in full.
"""

import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = True
ALLOW_MARKER = "check-def-commentary: allow"

ADVICE = (
    "move it to a #rem- div right after the definition (one div per "
    "subfile), or add <!-- check-def-commentary: allow --> if the sentence "
    "is part of the definition"
)

STARTERS = (
    r"It is not|It isn't|This is not|That is not|Note that|Notice that|"
    r"Unlike|Do not confuse|Don't confuse|Be careful|Beware|In contrast|"
    r"By contrast|Intuitively|Informally|Historically|"
    r"(?:This |It )?[Ee]xtends|(?:This |It )?[Gg]eneralizes|Just as|"
    r"Similarly|Equivalently|In other words|"
    r"For \$?[A-Za-z] ?= ?\d+\$?"
)
# A starter at the start of a line, or after a sentence end on the line.
COMMENTARY_RE = re.compile(r"(?:^\s*|(?<=[.!?])\s+)(" + STARTERS + r")\b")

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
DEF_ID_RE = re.compile(r"#def-")
CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")


class Finding(NamedTuple):
    line: int
    phrase: str


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


def scan_definitions(lines: List[str]) -> List[Finding]:
    """Commentary sentences that sit directly inside a ``#def-`` div."""
    findings: List[Finding] = []
    stack: List[bool] = []
    fence: Optional[Tuple[str, int]] = None
    in_math = in_comment = False
    for idx, original in enumerate(lines):
        raw = original
        if fence is None:
            raw, in_comment = strip_comment(raw, in_comment)
        m = FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
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
                stack.append(bool(DEF_ID_RE.search(dm.group(2))))
            elif stack:
                stack.pop()
            continue
        if not stack or not stack[-1] or ALLOW_MARKER in original:
            continue
        prose = CODE_SPAN_RE.sub(" ", raw)
        hit = COMMENTARY_RE.search(prose)
        if hit:
            findings.append(Finding(idx + 1, hit.group(1)))
    return findings


def format_message(phrase: str) -> str:
    return (f"Commentary inside a definition div (a sentence opening "
            f"\"{phrase}\"); a definition holds the definition, its "
            f"notation and its display equation only. Fix: {ADVICE}")


# -- Git plumbing ------------------------------------------------------------

compile_ignores = diffscope.compile_ignores
parse_diff = diffscope.parse_diff


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
            if not diffscope.ignored(rel, ignores):
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
        for found in scan_definitions(content):
            if keep is None or found.line in keep:
                findings.append((rel, found))
    return Report(findings, files, False)


def main() -> int:
    base_ref = os.environ.get("DCM_BASE_REF", "").strip()
    globs = os.environ.get("DCM_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(
        diffscope.split_list(os.environ.get("DCM_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("DCM_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("DCM_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the definition-commentary check for this run "
              f"({reason}; not falling back to a whole-tree scan, which would "
              f"reflag every definition the corpus already carries).")
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.files} file(s) (scope: {scope}).")
    severity = "error" if fail else "warning"
    for rel, found in report.findings:
        print(f"::{severity} file={rel},line={found.line}::{format_message(found.phrase)}")
    if not report.findings:
        print("No definition div carries commentary.")
        return 0
    print(f"\n{len(report.findings)} commentary sentence(s) inside definition divs.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
