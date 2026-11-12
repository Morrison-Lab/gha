#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a contrast ("X, not Y") in a definition, remark or note that cites no source.

The lab's rule (Ezra, 2026-10-28; Morrison-Lab/psw): a contrast the text keeps
must say who holds the other reading, with a source, so it is not a straw man.
If no source or reader holds the reading, the contrast is deleted. Example:
"Statistics uses predictor for a feature, not for a model" (lds#1565).

Whether anyone holds the other reading is a fact about the literature, so no
script can decide it. This check is a heuristic prompt for the author:
it flags the phrasing that usually signals such a contrast, in a ``#def-``,
``#rem-`` or ``#note-`` div that holds no citation.

What is flagged, in the prose of such a div: ", not for/as/a/an/the",
"does not mean", "do not mean", "not to be confused with" and
"rather than a/an". The finding sits on the line that holds the phrase.

What is not flagged:

- a div that holds a citation (``[@key``), since the source is the explanation;
- lines inside code fences, display math or HTML comments, and inline code;
- a line carrying ``<!-- check-unexplained-contrasts: allow -->``;
- a div whose id is not ``def-``, ``rem-`` or ``note-``.

"is not a/an" is not in the list, since most plain statements ("H is not a tree")
use it and a whole-tree run found it was mostly noise.
The remaining phrases were sampled over lds, mds, pds, sds and psw,
and each hit read as a real contrast (gha#1477).

Design notes, in the model of ``check-def-commentary``:

- **Diff-scoped by default.** Only an added line is reported. The whole file
  is parsed, since the div opens far above the line that changed. An added
  line whose exact text was also deleted in the diff counts as moved.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``UCT_WHOLE_TREE=true`` scans the
  whole tree, which measures how many existing contrasts lack a source.
- **Fails by default** (``UCT_FAIL`` defaults to true, gha#1477).

Configuration (environment variables, set by the composite action):
  UCT_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  UCT_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  UCT_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  UCT_FAIL          "false" => warning annotations only;
                    default "true".
  UCT_WHOLE_TREE    "true" => scan every tracked matching file in full.
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
ALLOW_MARKER = "check-unexplained-contrasts: allow"

ADVICE = (
    "say who holds the other reading and cite a source "
    "(psw: Do not rule out readings no reader would make), delete the "
    "contrast if nobody holds it, or add "
    "<!-- check-unexplained-contrasts: allow --> if it is a plain statement"
)

CONTRAST_RE = re.compile(
    r"(,\s+not\s+(?:for|as|a|an|the)\b"
    r"|\bdoes not mean\b|\bdo not mean\b"
    r"|\bnot to be confused with\b"
    r"|\brather than (?:a|an)\b)",
    re.IGNORECASE,
)
CITATION_RE = re.compile(r"\[-?@[A-Za-z0-9_]")
CONTRAST_ID_RE = re.compile(r"#(?:def|rem|note)-")

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")


class Finding(NamedTuple):
    line: int
    phrase: str


class _Frame:
    """One open div: whether it is read, its candidate hits, its citation."""

    def __init__(self, read: bool) -> None:
        self.read = read
        self.hits: List[Finding] = []
        self.cited = False


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


def scan_contrasts(lines: List[str]) -> List[Finding]:
    """Contrast phrases in a ``def-``/``rem-``/``note-`` div with no citation."""
    findings: List[Finding] = []
    stack: List[_Frame] = []
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
                stack.append(_Frame(bool(CONTRAST_ID_RE.search(dm.group(2)))))
            elif stack:
                frame = stack.pop()
                if frame.read and not frame.cited:
                    findings.extend(frame.hits)
            continue
        if not stack or not stack[-1].read:
            continue
        if CITATION_RE.search(raw):
            stack[-1].cited = True
        if ALLOW_MARKER in original:
            continue
        prose = mdmask.CODE_SPAN_RE.sub(" ", raw)
        hit = CONTRAST_RE.search(prose)
        if hit:
            stack[-1].hits.append(Finding(idx + 1, hit.group(1).strip(", ")))
    # A file with no div: nothing is read, so nothing is flagged.
    return sorted(findings)


def format_message(phrase: str) -> str:
    return (f"Contrast (\"{phrase}\") in a definition, remark or note that "
            f"cites no source; a kept contrast must say why a reader would "
            f"hold the other reading. Fix: {ADVICE}")


# -- Git plumbing ------------------------------------------------------------

# The diff-scoping helpers live in check-common/diffscope.py (gha#1856).
# parse_diff and compile_ignores keep their names here for the tests and
# callers that read them from this module.
parse_diff = diffscope.parse_diff
compile_ignores = diffscope.compile_ignores


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
        for found in scan_contrasts(content):
            if keep is None or found.line in keep:
                findings.append((rel, found))
    return Report(findings, files, False)


def main() -> int:
    base_ref = os.environ.get("UCT_BASE_REF", "").strip()
    globs = os.environ.get("UCT_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignore_list = diffscope.split_list(os.environ.get("UCT_PATHS_IGNORE", ""))
    ignores = diffscope.compile_ignores(ignore_list)
    fail = diffscope.env_flag("UCT_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("UCT_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the unexplained-contrasts check for this run "
              f"({reason}; not falling back to a whole-tree scan, which would "
              f"reflag every contrast the corpus already carries).")
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.files} file(s) (scope: {scope}).")
    severity = "error" if fail else "warning"
    for rel, found in report.findings:
        print(f"::{severity} file={rel},line={found.line}::{format_message(found.phrase)}")
    if not report.findings:
        print("No unexplained contrast found.")
        return 0
    print(f"\n{len(report.findings)} unexplained contrast(s).")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
