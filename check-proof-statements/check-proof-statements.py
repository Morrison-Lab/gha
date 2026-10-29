#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a proof hidden from the slides, and reasoning inside a theorem statement.

Two rules from Ezra (2026-10-29, Morrison-Lab/mds#534 review; Morrison-Lab/psw#426;
Morrison-Lab/gha#1351):

- **proof hidden from slides**: a proof inside ``::: {.content-hidden
  when-format="revealjs"}`` (or ``.content-visible unless-format="revealjs"``)
  is hidden from the deck. Every proof is shown on slides. The finding sits on
  the proof's opening line, or on an include of a ``_prf-`` / ``_proof-``
  subfile, and is reported when the pull request adds any line to the file
  (not only the proof's own lines), because the proof is read in the context of
  the file being edited. There is no sweep: an untouched file is never flagged.
- **reasoning in a theorem statement**: a line the pull request adds, inside a
  ``#thm-``, ``#lem-``, ``#cor-`` or ``#prp-`` div and outside any proof div it
  holds, that uses "so", "because", "hence", "therefore", "thus" or "since".
  A statement gives the result and its hypotheses; the proof gives the
  reasoning. Heuristic, so warn-only: "so that" and "so-called" pass, and words
  inside inline or display math, code and comments are not read.

The diff model, Markdown masking (code fences, spans, HTML comments, front
matter), skip-not-fall-back and the warn-only default come from
``check-write-idiom``, whose engine this script reuses; the div tracking and
rules are its own. Silence a line with ``<!-- check-proof-statements: allow
-->`` on it or on the line before.

Configuration (environment variables, set by the composite action):
  CPS_BASE_REF, CPS_GLOBS, CPS_PATHS_IGNORE, CPS_FAIL, CPS_WHOLE_TREE
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

DEFAULT_GLOBS = engine.DEFAULT_GLOBS
_DEFAULT_FAIL = engine._DEFAULT_FAIL
ALLOW_RE = re.compile(r"<!--\s*check-proof-statements:\s*allow\s*-->")
NEVER_RE = re.compile(r"(?!x)x")

DIV_RE = re.compile(r"^\s*(:{3,})\s*(.*?)\s*:*\s*$")
HIDDEN_RE = re.compile(
    r"(?:\.content-hidden\b[^}]*\bwhen-format\s*=\s*[\"'][^\"']*\brevealjs\b"
    r"|\.content-visible\b[^}]*\bunless-format\s*=\s*[\"'][^\"']*\brevealjs\b)")
PROOF_RE = re.compile(r"(?:^|[\s{])(?:\.proof\b|proof\b(?!-)|#prf-|\.proof-)")
THEOREM_RE = re.compile(r"#(?:thm|lem|cor|prp)-")
INCLUDE_RE = re.compile(r"\{\{<\s*include\s+(\S+)\s*>\}\}")
PROOF_FILE_RE = re.compile(r"(?:^|[/_])(?:prf|proof)[-_.]")
INLINE_MATH_RE = re.compile(r"\$\$.*?\$\$|\$[^$]*\$")
REASONING_RE = re.compile(
    r"(?i)\b(?:so(?!\s+that\b|-called\b|\s+far\b)|because|hence|therefore|thus|since)\b")

PROOF_MESSAGE = (
    "Show every proof on slides: remove the content-hidden wrapper around this "
    "proof (Ezra, 2026-10-29, mds#534; psw#426).")
STATEMENT_MESSAGE = (
    'A theorem statement gives the result and its hypotheses; move the reasoning '
    '("{word}") into the proof (Ezra, 2026-10-29, mds#534; psw#426).')


class Finding(NamedTuple):
    line: int
    rule: str
    phrase: str


def _classify(attrs: str) -> Set[str]:
    kinds: Set[str] = set()
    if HIDDEN_RE.search(attrs):
        kinds.add("hidden")
    if PROOF_RE.search(attrs):
        kinds.add("proof")
    if THEOREM_RE.search(attrs):
        kinds.add("theorem")
    return kinds


def scan_file(lines: List[str], keep: Optional[Set[int]] = None) -> Tuple[List[Finding], int]:
    """``([Finding, ...], lines examined)``; ``keep`` is the added-line set.

    ``keep`` of ``None`` means a whole-tree scan, where every file counts as touched.
    """
    touched = keep is None or bool(keep)
    stack: List[Set[str]] = []
    in_display = False

    def hidden_now() -> bool:
        return any("hidden" in kinds for kinds in stack)

    def step(masked: str) -> List[Tuple[str, str]]:
        nonlocal in_display
        div = DIV_RE.match(masked)
        if div and div.group(2):
            kinds = _classify(div.group(2))
            stack.append(kinds)
            if "proof" in kinds and hidden_now():
                return [("proof", "proof")]
            return []
        if div:
            if stack:
                stack.pop()
            return []
        include = INCLUDE_RE.search(masked)
        if include and PROOF_FILE_RE.search(include.group(1)) and hidden_now():
            return [("proof", "proof")]
        if masked.count("$$") % 2 == 1:
            in_display = not in_display
            return []
        if in_display or masked.lstrip().startswith("#"):
            return []
        for kinds in reversed(stack):
            if "proof" in kinds:
                return []
            if "theorem" in kinds:
                hit = REASONING_RE.search(INLINE_MATH_RE.sub(" ", masked))
                return [("statement", hit.group(0).lower())] if hit else []
        return []

    hits, examined = engine.scan_markdown(lines, step, NEVER_RE)
    findings: List[Finding] = []
    for number, (rule, phrase) in hits:
        allowed = ALLOW_RE.search(lines[number - 1]) or (
            number > 1 and ALLOW_RE.search(lines[number - 2]))
        if allowed:
            continue
        if rule == "proof":
            keep_it = touched
        else:
            keep_it = keep is None or number in keep
        if keep_it:
            findings.append(Finding(number, rule, phrase))
    return findings, examined


scan_file.wants_scope = True  # type: ignore[attr-defined]


def format_message(finding: Finding) -> str:
    if finding.rule == "proof":
        return PROOF_MESSAGE
    return STATEMENT_MESSAGE.format(word=finding.phrase)


def main() -> int:
    return engine.main(
        scan=scan_file, prefix="CPS_", name="proof-statements",
        clean="No hidden proof and no reasoning in a theorem statement found.",
        summary="hide a proof from slides or put reasoning in a theorem statement.",
        format_finding=format_message)


if __name__ == "__main__":
    sys.exit(main())
