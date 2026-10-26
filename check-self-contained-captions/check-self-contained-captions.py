#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a figure or table caption whose first sentence only points to another div.

The lab's rule (Ezra, 2026-10-26; Morrison-Lab/gha#1237): a caption states
what the figure or table shows, so it stands alone. A cross-reference may
support the claim ("... (@exm-x)"), and never replaces it. The motivating
caption was "The symmetry of @exm-logistic-symmetry.", which says nothing
until the reader follows the link.

Where a caption is found:

- the last paragraph of a ``#fig-`` or ``#tbl-`` div (the lab's div syntax),
  skipping a div whose last line closes a nested div or a code fence;
- a chunk option ``#| fig-cap: "..."`` or ``#| tbl-cap: "..."`` on one line;
- a pipe-table caption line ``: Caption {#tbl-x}``.

What is checked: the caption's first sentence, with inline code, link URLs,
and cross-references (``@fig-x``, ``[@exm-x]``, ``@sec-x``...) removed. It is
flagged only when it held a cross-reference and what is left either has fewer
than ``MIN_WORDS`` words or ends on a word that needs a complement ("of",
"at", "the"...). A first sentence with no cross-reference is never flagged,
so a short plain caption such as "Fitted line" passes.

A float is exempt when its div holds ``<!-- caption-ref: reason -->`` with a
non-empty reason. Whole paths are exempt through ``paths-ignore``.

Design notes, in the model of ``check-exm-figures``, whose parsing and git
helpers come from ``check-one-div-per-subfile``:

- **Diff-scoped by default.** A float is reported only when it holds a line
  the diff adds, so existing captions are never reflagged. An added line whose
  exact text was also deleted in the same diff is moved, and a blank added
  line is not content. ``SCC_WHOLE_TREE=true`` scans every tracked file.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning.
- **Blocking by default** (``SCC_FAIL`` defaults to true).
- **The search space is reported**: files, lines and captions examined.

Configuration (environment variables, set by the composite action):
  SCC_BASE_REF      Git ref/SHA to diff against.
  SCC_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  SCC_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  SCC_FAIL          "false" => warn only; default "true".
  SCC_WHOLE_TREE    "true" => scan every tracked matching file in full.
"""

import importlib.util
import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _load_sibling(name: str):
    """Import a sibling check's script, whose directory name has hyphens."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, os.pardir, name, name + ".py")
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ods = _load_sibling("check-one-div-per-subfile")

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = True
MIN_WORDS = 4
# A long first sentence that names its subject may end on "of @x" and still
# say what the float shows ("The residuals of the first five cars of @x").
SHORT_WORDS = 8

ADVICE = (
    "open the caption with a sentence that says what the float shows, and "
    "keep the cross-reference as support, or add "
    "<!-- caption-ref: reason --> inside the div"
)

FLOAT_RE = re.compile(r"#(?:fig|tbl)-")
EXEMPT_RE = re.compile(r"<!--\s*caption-ref:\s*(?!-->)\S")
CAPTION_OPTION_RE = re.compile(r"^\s*#\|\s*(?:fig|tbl)-cap:\s*(.*)$")
PIPE_CAPTION_RE = re.compile(r"^:\s+(.*?)\s*\{[^}]*#tbl-[^}]*\}\s*$")

INLINE_CODE_RE = re.compile(r"`[^`]*`")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
# Only a reference to a div or section counts; a bare citation key does not.
REF_PREFIX = r"@(?:fig|tbl|exm|exr|def|thm|lem|cor|prp|rem|cnj|alg|lst|sec|eq|apx)-"
BRACKET_REF_RE = re.compile(r"\[[^\]]*" + REF_PREFIX + r"[^\]]*\]")
REF_RE = re.compile(REF_PREFIX + r"[\w:.-]*\w")
SHORTCODE_RE = re.compile(r"\{\{<.*?>\}\}")
EMPTY_PARENS_RE = re.compile(r"\(\s*(?:see|cf\.?|in)?\s*\)", re.IGNORECASE)
# ", as in @x" or "(see @x)" after a complete clause only supports it.
SUPPORT_TAIL_RE = re.compile(
    r"(?:,|\()\s*(?:as in|as shown in|as for|see|cf\.?|compare|from)\s*\)?\s*(?=\s*$)",
    re.IGNORECASE)
SENTENCE_END_RE = re.compile(r"[.!?](?:\s|$)")
WORD_RE = re.compile(r"[A-Za-z0-9$\\][\w$\\'-]*")

DANGLING = {
    "a", "an", "the", "of", "to", "in", "at", "for", "from", "by", "with",
    "on", "and", "or", "than", "between", "under", "using", "see", "per",
    "against", "as", "about", "over", "into", "through", "among", "during",
}


class Caption(NamedTuple):
    start: int  # 1-based first line of the caption
    end: int    # 1-based last line of the caption
    text: str


def first_sentence_problem(text: str) -> Optional[str]:
    """Why the caption's first sentence only points elsewhere, else None."""
    flat = " ".join(text.split())
    flat = INLINE_CODE_RE.sub(" ", flat)
    flat = SHORTCODE_RE.sub("@ref", flat)
    flat = LINK_RE.sub(r"\1", flat)
    had_ref = bool(BRACKET_REF_RE.search(flat) or REF_RE.search(flat)
                   or "@ref" in flat)
    if not had_ref:
        return None
    flat = BRACKET_REF_RE.sub(" ", flat)
    flat = REF_RE.sub(" ", flat)
    flat = flat.replace("@ref", " ")
    flat = EMPTY_PARENS_RE.sub(" ", flat)
    m = SENTENCE_END_RE.search(flat)
    sentence = flat[:m.start()] if m else flat
    sentence = SUPPORT_TAIL_RE.sub("", sentence)
    words = WORD_RE.findall(sentence)
    if len(words) < MIN_WORDS:
        return f"its first sentence has only {len(words)} word(s) besides the cross-reference"
    if len(words) < SHORT_WORDS and words[-1].lower() in DANGLING:
        return f"its first sentence ends on '{words[-1]}', so it needs the cross-reference to make sense"
    return None


def scan_floats(lines: List[str]) -> List[Tuple[int, int, str, Optional[Caption]]]:
    """Every ``#fig-``/``#tbl-`` div outside code fences and HTML comments,
    as (start, end, attrs, caption). Also bare option and pipe captions,
    reported with their own line as the span."""
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    stack: List[Tuple[int, str]] = []
    found: List[Tuple[int, int, str, Optional[Caption]]] = []
    for idx, raw in enumerate(lines):
        if fence is None:
            raw, in_comment = ods.strip_comments(raw, in_comment)
        m = ods.FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            else:
                om = CAPTION_OPTION_RE.match(raw)
                if om:
                    text = om.group(1).strip().strip("\"'")
                    found.append((idx + 1, idx + 1, "chunk option",
                                  Caption(idx + 1, idx + 1, text)))
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        pm = PIPE_CAPTION_RE.match(raw)
        if pm:
            found.append((idx + 1, idx + 1, "pipe-table caption",
                          Caption(idx + 1, idx + 1, pm.group(1))))
            continue
        dm = ods.DIV_RE.match(raw)
        if not dm:
            continue
        if dm.group(2):
            stack.append((idx + 1, dm.group(2)))
        elif stack:
            start, attrs = stack.pop()
            if FLOAT_RE.search(attrs):
                found.append((start, idx + 1, attrs,
                              _last_paragraph(lines, start, idx + 1)))
    return found


def _is_boundary(line: str) -> bool:
    """A line that is a fence, a div fence or an HTML comment, not prose."""
    t = line.strip()
    return t.startswith((":::", "```", "~~~", "<!--")) or t.endswith("-->")


def _last_paragraph(lines: List[str], start: int, end: int) -> Optional[Caption]:
    """The paragraph just above the closing fence of lines[start-1:end]."""
    i = end - 2  # 0-based index of the line above the closing fence
    while i >= start and not lines[i].strip():
        i -= 1
    if i < start:
        return None
    if _is_boundary(lines[i]):
        return None
    j = i
    while j - 1 >= start and lines[j - 1].strip() and not _is_boundary(lines[j - 1]):
        j -= 1
    return Caption(j + 1, i + 1, " ".join(s.strip() for s in lines[j:i + 1]))


def scan_file(lines: List[str], keep: Optional[Set[int]]):
    """Findings (start, attrs, reason) that hold a kept line, and captions seen."""
    findings = []
    seen = 0
    for start, end, attrs, cap in scan_floats(lines):
        if cap is None:
            continue
        seen += 1
        body = lines[start - 1:end]
        if any(EXEMPT_RE.search(s) for s in body):
            continue
        reason = first_sentence_problem(cap.text)
        if reason is None:
            continue
        if keep is None or any(start <= n <= end for n in keep):
            findings.append((cap.start, attrs, reason))
    return findings, seen


def format_message(attrs: str, reason: str) -> str:
    ident = re.search(r"#(?:fig|tbl)-[\w:.-]+", attrs)
    name = ident.group(0) if ident else attrs
    return f"Caption of {name} is not self-contained: {reason}. Fix: {ADVICE}"


class Report(NamedTuple):
    findings: List[Tuple[str, int, str, str]]  # (path, line, attrs, reason)
    files: int
    lines: int
    captions: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: list,
              whole_tree: bool) -> Report:
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = ods._run_git(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, 0, 0, True)
        for rel in out.splitlines():
            if rel and not ods._ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, 0, True)
        base = ods._run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, 0, True)
        diff = ods._run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                             base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, 0, True)
        added, deleted = ods.parse_diff(diff)
        for rel, numbered in added.items():
            if ods._ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if text.strip() and text not in deleted}

    findings: List[Tuple[str, int, str, str]] = []
    files = lines = captions = 0
    for rel in sorted(wanted):
        content = ods._read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        found, seen = scan_file(content, keep)
        captions += seen
        findings.extend((rel, line, attrs, reason) for line, attrs, reason in found)
    return Report(findings, files, lines, captions, False)


def main() -> int:
    base_ref = os.environ.get("SCC_BASE_REF", "").strip()
    globs = os.environ.get("SCC_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = ods.compile_ignores(ods._split_list(os.environ.get("SCC_PATHS_IGNORE", "")))
    fail = ods._env_flag("SCC_FAIL", _DEFAULT_FAIL)
    whole_tree = ods._env_flag("SCC_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the caption check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every caption the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s), "
        f"{report.captions} caption(s) (scope: {scope})."
    )
    severity = "error" if fail else "warning"
    for rel, line, attrs, reason in report.findings:
        print(f"::{severity} file={rel},line={line}::{format_message(attrs, reason)}")
    if not report.findings:
        print("Every examined caption states what its float shows.")
        return 0
    print(f"\n{len(report.findings)} caption(s) only point to another div.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
