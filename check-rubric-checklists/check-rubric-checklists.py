#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a grading rubric that is not written as a checklist.

The lab's default (Ezra, 2026-10-26): most STEM grading rubrics are
checklists, one item per observable criterion, so a grader marks each item
earned or not. A rubric written as a paragraph, such as
"Grading (10 points): (a) 5, one per shape; (b) 5, two for ...", makes the
grader rebuild the items.

What is a rubric: a line that opens with ``Grading``, ``Rubric``, ``Marking
scheme`` or ``Mark scheme`` (bare, bolded, italic or in a blockquote, or as
a heading), followed by ``(``, ``:`` or the end of the line.

What is compliant: the rubric's block holds at least one task-list item
(``- [ ] ...``). The block is the marker line plus the lines after it that
are blank, list items or indented continuations; it stops at the first
other line.

What is not counted:

- text inside a code fence or an HTML comment;
- a rubric that carries ``<!-- rubric-ok: <reason> -->`` on its marker line,
  inside its block or on the line before it (for example a single holistic
  judgment that has no separable criteria).

Design notes, in the model of ``check-multipart-exercises``:

- **Diff-scoped by default.** A rubric is reported when the diff adds a line
  inside its block (marker included), so an old rubric the PR does not
  touch is never reflagged.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``RCL_WHOLE_TREE=true`` scans
  the whole tree to measure the corpus.
- **Warn-only by default** (``RCL_FAIL`` defaults to false): the rule is a
  default for *most* STEM rubrics, not an absolute one.

Configuration (environment variables, set by the composite action):
  RCL_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  RCL_GLOBS         Space-separated git pathspecs (default: '*.qmd *.md').
  RCL_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  RCL_FAIL          "true" => error annotations and a failing exit.
  RCL_WHOLE_TREE    "true" => scan every tracked matching file in full.
"""

import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "check-common"))
import diffscope  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd *.md"
_DEFAULT_FAIL = False

ADVICE = (
    "write the rubric as a checklist, one `- [ ] N points: criterion` item "
    "per observable criterion"
)

# -- Parsing -----------------------------------------------------------------

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
MARKER_RE = re.compile(
    r"^[ \t]*(?:>\s*)*(?:#{1,6}\s+)?[*_]*"
    r"(?:Grading|Rubric|Marking\s+scheme|Mark\s+scheme)"
    r"(?=[*_]*\s*(?:\(|:|$))",
    re.IGNORECASE,
)
TASK_RE = re.compile(r"^[ \t]*(?:>\s*)*[-*+]\s+\[[ xX]\]\s+\S")
LIST_RE = re.compile(r"^[ \t]*(?:>\s*)*(?:[-*+]|\d{1,3}[.)])\s+")
QUOTE_PREFIX_RE = re.compile(r"^[ \t]*(?:>[ ]?)+")
ALLOW_WORD_RE = re.compile(r"\brubric-ok\b", re.IGNORECASE)
ALLOW_RE = re.compile(r"<!--\s*rubric-ok\b", re.IGNORECASE)


class Rubric(NamedTuple):
    start: int  # line of the marker (1-based)
    end: int  # last line of the block
    has_checklist: bool
    allowed: bool


def strip_comments(raw: str, in_comment: bool) -> Tuple[str, bool]:
    """Remove HTML comment text from one line; say whether one stays open."""
    if in_comment:
        end = raw.find("-->")
        if end < 0:
            return "", True
        raw = raw[end + 3:]
    while True:
        start = raw.find("<!--")
        if start < 0:
            return raw, False
        end = raw.find("-->", start + 4)
        if end < 0:
            return raw[:start], True
        raw = raw[:start] + raw[end + 3:]


def find_rubrics(lines: List[str]) -> List[Rubric]:
    """Rubric blocks outside code fences."""
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    kept: List[Optional[str]] = []
    for raw in lines:
        text = raw
        if fence is None:
            text, in_comment = strip_comments(raw, in_comment)
        m = FENCE_RE.match(raw if fence is not None else text)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            kept.append(None)
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            kept.append(None)
            continue
        kept.append(text)

    found: List[Rubric] = []
    for idx, text in enumerate(kept):
        if text is None or not MARKER_RE.match(text):
            continue
        end = idx
        gap = False
        comment_lines = []
        has_list = bool(TASK_RE.match(text))
        for j in range(idx + 1, len(kept)):
            nxt = kept[j]
            if nxt is None:
                break
            if not nxt.strip("> \t"):
                if not lines[j].strip("> \t"):
                    gap = True
                elif not gap:
                    # Comment-only line: part of the block unless a blank line came first.
                    end = j
                    comment_lines.append(j)
                continue
            gap = False
            if TASK_RE.match(nxt):
                has_list = True
            elif not (LIST_RE.match(nxt) or QUOTE_PREFIX_RE.sub("", nxt)[:1] in (" ", "\t")):
                break
            end = j
        before = lines[idx - 1] if idx else ""
        allowed = (bool(ALLOW_RE.search(before))
                   or any(ALLOW_RE.search(lines[k]) for k in range(idx, end + 1))
                   or any(ALLOW_WORD_RE.search(lines[k]) for k in comment_lines))
        found.append(Rubric(idx + 1, end + 1, has_list, allowed))
    return found


def scan_file(lines: List[str]) -> Tuple[List[Rubric], int]:
    """Rubrics that are not checklists, and the number of rubrics seen."""
    rubrics = find_rubrics(lines)
    return [r for r in rubrics if not r.has_checklist and not r.allowed], len(rubrics)


def format_message() -> str:
    return (f"This grading rubric is not a checklist; most STEM rubrics are "
            f"(Ezra, 2026-10-26). Fix: {ADVICE}. "
            f"For a question with no separable criteria, add "
            f"<!-- rubric-ok: reason -->")


# -- Git plumbing ------------------------------------------------------------

# The diff-scoping helpers live in check-common/diffscope.py (gha#1856).


class Report(NamedTuple):
    findings: List[Tuple[str, int]]  # (path, marker line)
    files: int
    rubrics: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    """Scan rubrics with an added line since ``base_ref``, or all when whole-tree."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        paths = diffscope.git_paths(["ls-files", "--", *globs])
        if paths is None:
            return Report([], 0, 0, True)
        for rel in paths:
            if rel and not diffscope.ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, True)
        base = diffscope.run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, True)
        diff = diffscope.run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                                  base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, True)
        added, deleted = diffscope.parse_diff(diff)
        for rel, numbered in added.items():
            if diffscope.ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if text.strip() and text not in deleted}

    findings: List[Tuple[str, int]] = []
    files = rubrics = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        found, seen = scan_file(content)
        rubrics += seen
        for rubric in found:
            if keep is None or any(rubric.start <= n <= rubric.end for n in keep):
                findings.append((rel, rubric.start))
    return Report(findings, files, rubrics, False)


def main() -> int:
    base_ref = os.environ.get("RCL_BASE_REF", "").strip()
    globs = os.environ.get("RCL_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignore_list = diffscope.split_list(os.environ.get("RCL_PATHS_IGNORE", ""))
    ignores = diffscope.compile_ignores(ignore_list)
    fail = diffscope.env_flag("RCL_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("RCL_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the rubric checklist check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every rubric the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.rubrics} rubric(s) across {report.files} "
        f"file(s) (scope: {scope})."
    )
    severity = "error" if fail else "warning"
    for rel, line in report.findings:
        print(f"::{severity} file={rel},line={line}::{format_message()}")
    if not report.findings:
        print("No touched rubric is missing its checklist.")
        return 0
    print(f"\n{len(report.findings)} rubric(s) are not checklists.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
