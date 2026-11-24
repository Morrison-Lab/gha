#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a double inequality in math, where interval membership says it once.

The rule is psw's "Avoiding double inequalities"
(https://morrison-lab.github.io/psw/notation.html#avoiding-double-inequalities):
prefer ``x \in (a, b)`` to ``a < x < b``, and ``p \in [0, 1]`` to
``0 \le p \le 1``. Ezra asked on Morrison-Lab/pds#492 (2026-11-24) why an
agent wrote ``0 < \varpar < \infty``; no check flagged it.

What is flagged, in ``$...$`` and ``$$...$$`` math of ``.qmd``, ``.md`` and
``.Rmd`` files: a clause made of exactly three operands joined by two order
relations that point the same way (``<``, ``\le``, ``\lt``, ``\leq``,
``\leqslant``, ``\preceq`` ... or their ``>`` mirrors), such as ``a < x \le b``.
A group (parentheses, braces, a macro argument such as ``\Pr{a < X \le b}``) is
checked on its own, so the event inside a probability is a clause too.

A clause ends at a separator (``,``, ``;``, ``:``, ``&``, ``\\``, ``\quad``,
``\text``, a quantifier) or a logical connective (``\land``, ``\implies`` ...),
using check-precedence-parens' tokenizer and parser.

What is not flagged:

- a chain of three or more relations (``x_1 < x_2 < \dots < x_n``), or one
  mixing in ``=`` (``a \le b = c``), which is an ordering or a derivation,
  not a constraint on one quantity;
- relations that point opposite ways (``a < x > b``);
- code fences and code spans, HTML comments, and YAML front matter;
- a line carrying, or following,
  ``<!-- check-double-inequalities: allow: <reason> -->``. The reason is
  required, as for check-ball-neighborhoods.

Diff-scoped, skip-not-fall-back, moved lines exempt and blocking by default,
in the model of check-precedence-parens. Env vars use the ``CDI_`` prefix:
  CDI_BASE_REF     Git ref/SHA to diff against. Empty and not whole-tree =>
                   skip the check.
  CDI_GLOBS        Space-separated git pathspecs.
  CDI_PATHS_IGNORE Comma/newline-separated glob patterns to skip.
  CDI_FAIL         "false" => warn only.
  CDI_WHOLE_TREE   "true" => scan every tracked matching file in full.
"""

import importlib.util
import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, "check-common"))
import diffscope  # noqa: E402
import mdmask  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "check_precedence_parens",
    os.path.join(HERE, os.pardir, "check-precedence-parens", "check-precedence-parens.py"))
cpp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cpp)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd *.Rmd *.md"
_DEFAULT_FAIL = True

ALLOW_RE = re.compile(r"<!--\s*check-double-inequalities:\s*allow:\s*\S[^>]*?-->")

LESS = {"<", r"\lt", r"\le", r"\leq", r"\leqslant", r"\prec", r"\preceq",
        "≤", "≺", "⪯"}
GREATER = {">", r"\gt", r"\ge", r"\geq", r"\geqslant", r"\succ", r"\succeq",
           "≥", "≻", "⪰"}
# Every relation ends an operand, so "a \le b = c" has three relations.
RELATIONS = set(cpp.RELATIONS) | LESS | GREATER
BREAKS = set(cpp.SEPARATORS) | set(cpp.CONNECTIVES)


class Finding(NamedTuple):
    line: int
    detail: str  # the clause as written


def _direction(tok: str) -> Optional[str]:
    if tok in LESS:
        return "less"
    if tok in GREATER:
        return "greater"
    return None


def check_group(group) -> List[str]:
    """The double-inequality clauses in this group and every group inside it."""
    found: List[str] = []
    for item in group.items:
        if isinstance(item, cpp.Group):
            found.extend(check_group(item))
    for _, clause in cpp._split(group.items, lambda t: t in BREAKS):
        parts = cpp._split(clause, lambda t: isinstance(t, str) and t in RELATIONS)
        relations = [rel for rel, _ in parts[1:]]
        if len(relations) != 2 or any(not operand for _, operand in parts):
            continue
        directions = {_direction(rel) for rel in relations}
        if len(directions) == 1 and None not in directions:
            found.append(cpp._render(clause))
    return found


def check_math(math: str) -> List[str]:
    return check_group(cpp.parse(cpp.tokenize(math)))


def scan_file(lines: List[str]) -> Tuple[List[Finding], int]:
    """``([Finding, ...], lines examined)`` for a Markdown-family file."""
    found: List[Finding] = []
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    in_display = False
    in_front = bool(lines) and lines[0].strip() == "---"
    for number, raw in enumerate(lines, 1):
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
        spans, in_display = mdmask.math_spans(masked, in_display)
        if ALLOW_RE.search(raw) or (number > 1 and ALLOW_RE.search(lines[number - 2])):
            continue
        for start, end in spans:
            found.extend(Finding(number, detail) for detail in check_math(masked[start:end]))
    return found, len(lines)


def format_message(finding: Finding) -> str:
    return (f"Write the double inequality '{finding.detail}' as interval "
            f"membership, such as x \\in (a, b) for a < x < b "
            f"(psw: Avoiding double inequalities).")


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
    files: int
    lines: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores, whole_tree: bool) -> Report:
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
        for finding in scan_file(content)[0]:
            if keep is None or finding.line in keep:
                findings.append((rel, finding))
    return Report(findings, files, lines, False)


def main() -> int:
    base_ref = os.environ.get("CDI_BASE_REF", "").strip()
    globs = os.environ.get("CDI_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = diffscope.compile_ignores(
        diffscope.split_list(os.environ.get("CDI_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("CDI_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("CDI_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)
    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the double-inequality check for this run "
              f"({reason}; not falling back to a whole-tree scan, which would "
              f"reflag every double inequality the repository already has).")
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.lines} line(s) across {report.files} file(s) "
          f"for double inequalities (scope: {scope}).")
    if not report.findings:
        print("No double inequalities.")
        return 0
    severity = "error" if fail else "warning"
    for rel, finding in report.findings:
        print(f"::{severity} file={rel},line={finding.line}::{format_message(finding)}")
    print(f"\n{len(report.findings)} double inequalit(y/ies).")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
