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
KEY_VALUE_RE = re.compile(r"""([\w-]+)\s*=\s*("[^"]*"|'[^']*'|[^\s}]+)""")
THEOREM_ID_RE = re.compile(r"(?:thm|lem|cor|prp)-")
INCLUDE_RE = re.compile(r"\{\{<\s*include\s+(\S+)\s*>\}\}")
PROOF_FILE_RE = re.compile(r"(?:^|[/_])(?:prf|proof)[-_.]")
INLINE_MATH_RE = re.compile(r"\$[^$]*\$")
# Text that is not prose: link targets, autolinks and URLs, cross-references,
# and a trailing `{#id}` or `{.class}` attribute block.
NON_PROSE_RE = re.compile(
    r"\]\([^)]*\)|<[^>\s]*>|https?://\S+|@[\w:.-]+|\{[#.][^}]*\}")
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
    """Kinds (``hidden``, ``proof``, ``theorem``) of a div from its attribute text.

    The attribute text is read as tokens, so attribute order and quoting do not
    matter and a word inside a quoted value (``title="a proof of concept"``) is
    not a class.
    """
    values = {key: value.strip("\"'") for key, value in KEY_VALUE_RE.findall(attrs)}
    tokens = KEY_VALUE_RE.sub(" ", attrs).replace("{", " ").replace("}", " ").split()
    classes = {t[1:] for t in tokens if t.startswith(".")}
    ids = {t[1:] for t in tokens if t.startswith("#")}
    bare = {t for t in tokens if t[0] not in ".#"}
    kinds: Set[str] = set()
    when = values.get("when-format", "").replace(",", " ").split()
    unless = values.get("unless-format", "").replace(",", " ").split()
    if ("content-hidden" in classes and "revealjs" in when) or \
            ("content-visible" in classes and "revealjs" in unless):
        kinds.add("hidden")
    if "proof" in classes or "proof" in bare \
            or any(c.startswith("proof-") for c in classes) \
            or any(i.startswith("prf-") for i in ids):
        kinds.add("proof")
    if any(THEOREM_ID_RE.match(i) for i in ids):
        kinds.add("theorem")
    return kinds


def _outside_math(line: str, in_display: bool) -> Tuple[str, bool]:
    """The text of ``line`` outside ``$$...$$`` and ``$...$``, and the display
    state at its end. A ``$$`` toggles display math wherever it falls on the line.
    """
    parts = line.split("$$")
    prose = [part for index, part in enumerate(parts) if (index % 2 == 1) == in_display]
    text = INLINE_MATH_RE.sub(" ", " ".join(prose))
    return text, in_display != (len(parts) % 2 == 0)


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
        prose, in_display = _outside_math(masked, in_display)
        if masked.lstrip().startswith("#"):
            return []
        for kinds in reversed(stack):
            if "proof" in kinds:
                return []
            if "theorem" in kinds:
                hit = REASONING_RE.search(NON_PROSE_RE.sub(" ", prose))
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
