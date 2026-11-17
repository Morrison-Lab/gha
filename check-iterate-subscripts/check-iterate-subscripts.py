#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a gradient-descent iterate written with a subscript, such as ``\vcoef_t``.

The lab's rule (psw ``chapters/notation/delimiters-and-scripts.qmd``, from
Morrison-Lab/psw#543): an iteration index goes in a parenthesized superscript,
written with the macros ``\iter`` and ``\iterpoint{\vcoef}{\iter}``, so the
iterate is ``\iterpoint{\vcoef}{\iter}`` and not ``\vcoef_t`` or
``\vcoef_{t+1}`` (Morrison-Lab/lds#2435).

What is flagged: in ``.qmd``, ``.md`` and ``.Rmd`` files, a configured symbol
(``CIS_SYMBOLS``, default ``vcoef`` and ``steplen``) followed by ``_`` and an
iteration index, bare (``\vcoef_t``) or braced (``\vcoef_{t}``,
``\vcoef_{t-1}``, ``\vcoef_{\iter+1}``). An index is a configured letter or
macro (``CIS_INDICES``, default ``t`` and ``\iter``) with an optional
``+`` or ``-`` and a number. The message is
``\vcoef_{t+1} -> \iterpoint{\vcoef}{t+1}``.

What is not flagged:

- an index that is a number alone, such as ``\vcoef_0``, because a true
  parameter has that name and only the caller knows which it is;
- a letter that is not in ``CIS_INDICES``, such as ``\vcoef_k`` by default,
  because ``k`` often names a coordinate (add it where it is an iteration);
- a symbol not in ``CIS_SYMBOLS``;
- code fences and code spans, HTML comments, and YAML front matter;
- a line carrying, or following, ``<!-- check-iterate-subscripts: allow -->``.

Design notes, in the model of ``check-fform-paren``:

- **Diff-scoped by default.** Only lines *added* since ``CIS_BASE_REF`` are
  reported, so existing pages never block. An added line whose exact text was
  also deleted in the same diff is treated as moved.
  ``CIS_WHOLE_TREE=true`` scans everything.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning instead of scanning the whole tree.
- **Blocks by default** (``CIS_FAIL`` defaults to true): the rule is
  deterministic once the symbols and indices are named.
- **The search space is reported.** Every run prints how many files and lines
  it examined.

Configuration (environment variables, set by the composite action):
  CIS_BASE_REF     Git ref/SHA to diff against. Empty and not whole-tree =>
                   skip the check.
  CIS_SYMBOLS      Space/comma-separated macro names, without the backslash.
  CIS_INDICES      Space/comma-separated index letters or macros, for example
                   ``t \iter``.
  CIS_GLOBS        Space-separated git pathspecs.
  CIS_PATHS_IGNORE Comma/newline-separated glob patterns to skip (``*``,
                   ``?`` and recursive ``**``).
  CIS_FAIL         "false" => warn only.
  CIS_WHOLE_TREE   "true" => scan every tracked matching file in full.
"""

import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402
import mdmask  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd *.Rmd *.md"
DEFAULT_SYMBOLS = "vcoef steplen"
DEFAULT_INDICES = r"t \iter"
_DEFAULT_FAIL = True

ALLOW_RE = re.compile(r"<!--\s*check-iterate-subscripts:\s*allow\s*-->")


class Finding(NamedTuple):
    line: int
    symbol: str
    index: str


def split_words(value: str) -> List[str]:
    """Words of a space- or comma-separated list."""
    return [word for word in re.split(r"[\s,]+", value.strip()) if word]


def build_pattern(symbols: List[str], indices: List[str]) -> "re.Pattern[str]":
    r"""The regex for ``\symbol_index`` and ``\symbol_{index}``.

    An index is one of ``indices``, then an optional ``+`` or ``-`` and a
    number. A bare index must not run into a following letter or digit
    (``\vcoef_tx`` is not an iterate).
    """
    names = "|".join(re.escape(s) for s in symbols)
    letters = "|".join(re.escape(i) for i in sorted(indices, key=len, reverse=True))
    index = rf"(?:{letters})(?:\s*[+-]\s*\d+)?"
    return re.compile(
        rf"(?<!\\)\\(?P<symbol>{names})(?![A-Za-z])\s*_\s*"
        rf"(?:\{{\s*(?P<braced>{index})\s*\}}"
        rf"|(?P<bare>(?:{letters})(?![A-Za-z0-9])))"
    )


def iterate_uses(text: str, pattern: "re.Pattern[str]") -> List[Tuple[str, str]]:
    """``(symbol, index)`` for each subscripted iterate of ``text``."""
    return [(m.group("symbol"), (m.group("braced") or m.group("bare")).strip())
            for m in pattern.finditer(text)]


def scan_file(lines: List[str], pattern: "re.Pattern[str]") -> Tuple[List[Finding], int]:
    """``([Finding, ...], lines examined)`` for a Markdown-family file."""
    found: List[Finding] = []
    examined = 0
    fence: Optional[Tuple[str, int]] = None  # (marker, length)
    in_comment = False
    in_front = bool(lines) and lines[0].strip() == "---"
    for number, raw in enumerate(lines, 1):
        examined += 1
        if in_front:
            if number > 1 and raw.strip() in ("---", "..."):
                in_front = False
            continue
        m = mdmask.FENCE_RE.match(raw)
        if fence is None and m and not in_comment:
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                    and not m.group(2):
                fence = None
            continue
        masked, in_comment = mdmask.mask_markdown_line(raw, in_comment)
        allowed = ALLOW_RE.search(raw) or (
            number > 1 and ALLOW_RE.search(lines[number - 2]))
        if not allowed:
            found.extend(Finding(number, s, i)
                         for s, i in iterate_uses(masked, pattern))
    return found, examined


def format_message(finding: Finding) -> str:
    s, i = finding.symbol, finding.index
    return (f"\\{s}_{{{i}}} -> \\iterpoint{{\\{s}}}{{{i}}}: write an iteration "
            f"index in a parenthesized superscript with \\iterpoint (psw "
            f"notation rule).")


# The git, glob and file helpers come from check-common (gha#1856).
compile_globs = diffscope.compile_ignores


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
    files: int
    lines: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              pattern: "re.Pattern[str]", whole_tree: bool) -> Report:
    """Scan the added lines since ``base_ref``, or every line when whole-tree."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        paths = diffscope.git_paths(["ls-files", "--", *globs])
        if paths is None:
            return Report([], 0, 0, True)
        for rel in paths:
            if not diffscope.ignored(rel, ignores):
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
                           if not (text.strip() and text in deleted)}

    findings: List[Tuple[str, Finding]] = []
    files = lines = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        for finding in scan_file(content, pattern)[0]:
            if keep is None or finding.line in keep:
                findings.append((rel, finding))
    return Report(findings, files, lines, False)


def main() -> int:
    base_ref = os.environ.get("CIS_BASE_REF", "").strip()
    symbols = split_words(os.environ.get("CIS_SYMBOLS", "")) or DEFAULT_SYMBOLS.split()
    indices = split_words(os.environ.get("CIS_INDICES", "")) or DEFAULT_INDICES.split()
    globs = os.environ.get("CIS_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_globs(diffscope.split_list(os.environ.get("CIS_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("CIS_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("CIS_WHOLE_TREE", False)
    pattern = build_pattern(symbols, indices)

    report = run_check(base_ref, globs, ignores, pattern, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        # With no base-ref (a push run) the skip is expected, so it is not an annotation.
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the iterate-subscript check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every subscripted iterate the repository already has)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    shown = ", ".join(chr(92) + s for s in symbols)
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s) "
        f"for subscripted iterates of {shown} (scope: {scope})."
    )
    if not report.findings:
        print("No subscripted iterates.")
        return 0

    severity = "error" if fail else "warning"
    for rel, finding in report.findings:
        print(f"::{severity} file={rel},line={finding.line}::"
              f"{format_message(finding)}")
    print(f"\n{len(report.findings)} subscripted iterate(s).")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
