#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag words and phrases that a style source advises against, in prose.

Four rules; the first three each have a source that was read (psw#418),
and the fourth is psw's own (psw#427):

- **position words**: ``above`` or ``below`` used for a place in the
  document, such as "the table above" or "as shown below". Refer to the
  result by its label instead. Source: Google developer documentation style
  guide, word list, entries "above" and "below" ("Don't use to refer to a
  position in a document").
- **effort words**: ``just``, ``easy``, ``easily``. Source: the same word
  list ("just": "Avoid. Usually, just is a filler word that you can delete
  without affecting your meaning"; "easy, easily": "Try eliminating this
  word").
- **time-relative words**: ``currently``, ``recently``, ``nowadays``, ``at
  present``, ``at the moment``, ``these days``. Source: Google, "Timeless
  documentation" ("Words like now, new, and currently can render such
  documentation inaccurate, outdated, or unmeaningful"). ``now`` and ``new``
  are not flagged because "now" and the term "new observation" are common
  correct uses a regex cannot tell apart; review covers them. ``recently`` is
  psw's own extension, which the guide does not list.
- **generic placeholders**: a domain, codomain, range or sample space named
  by a bare capital letter ("domain A", "range B") or by "some" ("some
  domain"). Name the specific set, such as "the range of X". Source: psw's
  "be as specific as feasible" (psw#427). A regex cannot know whether a
  specific object exists, so a finding only asks the author to check; a
  deliberate abstract use takes the allow comment.

What is flagged is deliberately narrow. ``above`` and ``below`` are flagged
only in the position senses (after a document noun, after "as shown/noted/..."
or at the end of a clause); "above the threshold" passes. ``just`` is not
flagged before ``before``, ``after``, ``as``, ``like``, ``then``, ``enough``,
``in time``, ``once`` or ``now``.

The diff model, Markdown masking (code fences and spans, HTML comments, front
matter), the ``<!-- check-avoided-words: allow -->`` comment, skip-not-fall-back
and warn-only default all come from ``check-write-idiom``, whose engine this
script reuses; only the rules below and the ``CAW_`` env prefix are its own.
It reports at most one finding per rule per line.

Configuration (environment variables, set by the composite action):
  CAW_BASE_REF, CAW_GLOBS, CAW_PATHS_IGNORE, CAW_FAIL, CAW_WHOLE_TREE
as for ``check-write-idiom`` (see its docstring).
"""

import importlib.util
import re
import sys
from pathlib import Path
from typing import List, NamedTuple, Tuple

_ENGINE_PATH = Path(__file__).resolve().parent.parent / "check-write-idiom" / "check-write-idiom.py"
_spec = importlib.util.spec_from_file_location("check_write_idiom_engine", _ENGINE_PATH)
assert _spec is not None and _spec.loader is not None
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)

DEFAULT_GLOBS = engine.DEFAULT_GLOBS
_DEFAULT_FAIL = engine._DEFAULT_FAIL
ALLOW_RE = re.compile(r"<!--\s*check-avoided-words:\s*allow\s*-->")

POSITION_NOUNS = (
    "equation|formula|figure|table|result|theorem|lemma|corollary|definition|"
    "example|exercise|section|derivation|code|text|list|plot|chart|"
    "expression|model|step|line|paragraph|argument|proof|solution|passage|"
    "display|inequality|identity|chunk|output|remark|proposition"
)
ASAS = (
    "shown|noted|stated|discussed|described|seen|mentioned|derived|defined|"
    "proved|explained|computed|given|illustrated|see"
)
POSITION_RE = re.compile(
    r"(?i)\b(?:the|this|that|these|those)\s+(?:\w+\s+)?(?:" + POSITION_NOUNS
    + r")s?\s+(above|below)\b"
    r"|\b(?:" + ASAS + r")\s+(above|below)\b"
    r"|,\s*(above|below)\s*[.,;:)]"
)
EFFORT_RE = re.compile(
    r"(?i)\b(?:just(?!\s+(?:before|after|as|like|then|enough|in\s+time|once|"
    r"now)\b)|easy|easily)\b"
)
TIME_RE = re.compile(
    r"(?i)\b(?:currently|recently|nowadays|at\s+present|at\s+the\s+moment|"
    r"these\s+days)\b"
)
GENERIC_RE = re.compile(
    r"\b(?:(?i:domain|codomain|range|sample\s+space)\s+[A-Z]\b(?![\w$\\(])"
    r"|(?i:some\s+(?:domain|codomain|range|sample\s+space)\b))"
)
RULES = (
    ("position", POSITION_RE,
     'Refer to a place in the document by its label, not "above" or "below"; '
     "the same source renders in several formats (psw#418; Google style guide, "
     'word list, entries "above" and "below").'),
    ("effort", EFFORT_RE,
     'Delete "just", "easy" and "easily" unless they carry meaning; they '
     "judge difficulty or add nothing (psw#418; Google style guide, word list)."),
    ("time", TIME_RE,
     "Give a date or a version instead of a time-relative word; it goes stale "
     "(psw#418; Google style guide, Timeless documentation)."),
    ("generic", GENERIC_RE,
     'Name the specific set, such as "the range of X", instead of a '
     "generic placeholder; be as specific as feasible (psw#427)."),
)


class Finding(NamedTuple):
    line: int
    rule: str
    phrase: str


def _find(masked: str) -> List[Tuple[str, str]]:
    """``(rule, phrase)`` for the first match of each rule on a masked line."""
    out = []
    for rule, pattern, _message in RULES:
        hit = pattern.search(masked)
        if hit:
            out.append((rule, hit.group(0).strip()))
    return out


def scan_file(lines: List[str]) -> Tuple[List[Finding], int]:
    """``([Finding, ...], lines examined)`` for a Markdown-family file."""
    hits, examined = engine.scan_markdown(lines, _find, ALLOW_RE)
    return [Finding(number, rule, phrase) for number, (rule, phrase) in hits], examined


def format_message(finding: Finding) -> str:
    message = {rule: text for rule, _pattern, text in RULES}[finding.rule]
    return f'"{finding.phrase}": {message}'


def main() -> int:
    return engine.main(
        scan=scan_file, prefix="CAW_", name="avoided-words",
        clean="No position, effort, time-relative or generic-placeholder word found.",
        summary="use a word a style source advises against.",
        format_finding=format_message)


if __name__ == "__main__":
    sys.exit(main())
