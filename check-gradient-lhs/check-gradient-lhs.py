#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a stated gradient whose symbol is not the left-hand side.

The psw rule (Morrison-Lab/psw#488, Morrison-Lab/psw#489; Morrison-Lab/gha#1538):
when a page states a gradient, it writes the symbol as the left-hand side of an
equation, ``\gradf{f}(\vx) = ...``, and not "Its gradient is ...".

A line a pull request adds is flagged when its prose has the word "gradient"
followed by "is" or "equals" and then math, a colon, or the end of the line
(a display equation follows), and no ``\grad``, ``\gradf``, ``\gradwrt`` or
``\nabla`` appears before the first ``=`` of that equation.
"The gradient is zero at the minimum" passes, since no equation follows.

This is a heuristic, so it warns by default (``fail: false``) and the opt-out is
``<!-- check-gradient-lhs: allow -->`` on the line or the line before.
The diff model, Markdown masking and skip-not-fall-back come from
``check-write-idiom``, whose engine this script reuses.

Configuration (environment variables, set by the composite action):
  CGL_BASE_REF, CGL_GLOBS, CGL_PATHS_IGNORE, CGL_FAIL, CGL_WHOLE_TREE
as for ``check-write-idiom`` (see its docstring).
"""

import importlib.util
import re
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional, Set, Tuple

_ENGINE_PATH = Path(__file__).resolve().parent.parent / "check-write-idiom" / "check-write-idiom.py"
_spec = importlib.util.spec_from_file_location("check_write_idiom_engine", _ENGINE_PATH)
assert _spec is not None and _spec.loader is not None
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)

DEFAULT_GLOBS = "*.qmd *.md"
_DEFAULT_FAIL = False
ALLOW_RE = re.compile(r"<!--\s*check-gradient-lhs:\s*allow\s*-->")
NEVER_RE = re.compile(r"(?!x)x")

# Words that make "gradient" part of a compound noun, as in "gradient descent are".
COMPOUND_WORDS = (
    "descent|ascent|boosting|clipping|norm|method|methods|step|steps|algorithm|"
    "flow|vanishing|exploding|checkpointing|accumulation")
# A link target or a crossref id can carry the word "gradient" without stating one.
LINK_TARGET_RE = re.compile(r"\]\([^)]*\)")
CROSSREF_RE = re.compile(r"@[\w:.-]+")
URL_RE = re.compile(r"https?://\S+")
# Math that is only a zero states a condition ("where its gradient is $\vzero$"), not a gradient.
ZERO_RE = re.compile(r"\s*(?:0|\\[vm]?zero(?:_\{[^}]*\}|_\w)?)\s*")
CONDITION_LEAD_RE = re.compile(
    r"(?i)\b(?:where|when|whenever|if|unless|makes?|exactly when|"
    r"(?:component|entry|coordinate)s? of)\b")
FIRST_MATH_RE =re.compile(r"\$([^$]*)\$")

# "gradient ... is|equals" followed by math, a colon, or the end of the line.
STATED_RE = re.compile(
    r"(?i)\bgradients?\b(?!\s+(?:" + COMPOUND_WORDS + r")\b)[^$.;:]{0,40}?\b(?:is|are|equals?)\b(?P<rest>(?:\s*[:$].*|\s*)$)")
GRAD_SYMBOL_RE = re.compile(r"\\(?:grad[A-Za-z]*|nabla)\b")
LOOKAHEAD_LINES = 8

MESSAGE = (
    "Write a stated gradient with its symbol as the left-hand side, such as "
    "`\\gradf{f}(\\vx) = ...`, not \"the gradient is ...\" (psw#488; gha#1538).")


class Finding(NamedTuple):
    line: int
    rule: str
    phrase: str


def _before_first_equals(text: str) -> Optional[str]:
    """The text before the first ``=`` in ``text``, or None when it has none."""
    index = text.find("=")
    return None if index < 0 else text[:index]


def _display_before_equals(lines: List[str], start: int) -> Optional[str]:
    """Text of the next display equation up to its first ``=``, if one follows.

    ``start`` is the 0-based index of the line after the candidate. Blank lines
    are skipped; any other prose before a ``$$`` means no equation follows.
    """
    collected: List[str] = []
    opened = False
    for line in lines[start:start + LOOKAHEAD_LINES]:
        if not opened:
            if not line.strip():
                continue
            if not line.lstrip().startswith("$$"):
                return None
            opened = True
            line = line.lstrip()[2:]
        collected.append(line)
        head = _before_first_equals(" ".join(collected))
        if head is not None:
            return head
        if "$$" in line:
            return None
    return None


def _strip_references(masked: str) -> str:
    """``masked`` without link targets, crossref ids and bare URLs."""
    masked = LINK_TARGET_RE.sub("]", masked)
    masked = URL_RE.sub("", masked)
    return CROSSREF_RE.sub("@", masked)


def _is_zero_condition(before: str, rest: str) -> bool:
    """True for a subordinate clause whose math is only a zero.

    ``before`` is the text ahead of "gradient". "The gradient equals $\vzero$"
    as a main clause still states a gradient, so a condition needs a lead-in
    such as "where", "when", "makes" or "component of".
    """
    math = FIRST_MATH_RE.search(rest)
    return bool(math and ZERO_RE.fullmatch(math.group(1)) and CONDITION_LEAD_RE.search(before))


def _is_stated_gradient(masked: str, lines: List[str], index: int) -> bool:
    """True when the candidate at 0-based ``index`` states a gradient with no symbol on the left."""
    cleaned = _strip_references(masked)
    hit = STATED_RE.search(cleaned)
    if not hit:
        return False
    rest = hit.group("rest")
    if "$" in rest:
        if _is_zero_condition(cleaned[:hit.start()], rest):
            return False
        head = _before_first_equals(rest)
        if head is None:
            return True  # math with no equation: the gradient is given by value only
        return not GRAD_SYMBOL_RE.search(head)
    head = _display_before_equals(lines, index + 1)
    return head is not None and not GRAD_SYMBOL_RE.search(head)


def scan_file(lines: List[str], keep: Optional[Set[int]] = None) -> Tuple[List[Finding], int]:
    """``([Finding, ...], lines examined)``; ``keep`` is the added-line set."""
    hits, examined = engine.scan_markdown(
        lines, lambda masked: [masked] if STATED_RE.search(_strip_references(masked)) else [], ALLOW_RE)
    findings: List[Finding] = []
    for number, masked in hits:
        if keep is not None and number not in keep:
            continue
        if _is_stated_gradient(masked, lines, number - 1):
            findings.append(Finding(number, "gradient-lhs", "gradient"))
    return findings, examined


scan_file.wants_scope = True  # type: ignore[attr-defined]


def format_message(finding: Finding) -> str:
    return MESSAGE


def main() -> int:
    return engine.main(
        scan=scan_file, prefix="CGL_", name="gradient-lhs",
        clean="No stated gradient without its symbol on the left found.",
        summary="state a gradient without its symbol on the left.",
        format_finding=format_message, default_fail=_DEFAULT_FAIL)


if __name__ == "__main__":
    sys.exit(main())
