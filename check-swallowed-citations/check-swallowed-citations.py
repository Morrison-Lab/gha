#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a citation that an in-text cross-reference just before it swallows.

Pandoc reads an in-text citation ``@key`` followed by a bracket as one
citation with a suffix (``@key [p. 3]``), and it reads a cross-reference such
as ``@eq-x`` with the same grammar. So in

    ... as in @eq-recurrent-layer
    [@pascanu2014construct, section 3.3.2].

the bracket becomes part of the ``@eq-recurrent-layer`` citation, and the
Pascanu citation drops out of the rendered page with no warning
(Morrison-Lab/lds#3239). Checked with ``quarto pandoc -t native`` (Quarto
1.10): ``@eq-a [@b]`` and ``@eq-a`` then ``[@b, section 3]`` on the next line
each parse as a single ``Cite`` that holds both ids.

What is flagged, in ``.qmd`` and ``.md`` files: an in-text cross-reference
(``@fig-``, ``@eq-``, ``@def-`` and the other Quarto prefixes) followed, with
only spaces or one line break between them, by a bracket that holds a
citation (``[@key``, ``[-@key``, ``[see @key``). The fix is to move the
citation, or to put a word or punctuation between the two:
``as in @eq-x, following [@key]``.

What is not flagged:

- a cross-reference followed by punctuation, such as ``@eq-x. [@key]`` or
  ``@eq-x, [@key]``, since the punctuation ends the citation;
- a cross-reference inside a bracket citation, such as ``[@eq-x] [@key]``;
- a bracket that is a link, ``[@key](url)``, or a bracket with no citation;
- an ordinary citation followed by a bracket (``@key [@other]``), which is
  outside this check's scope;
- a blank line between the two, since a paragraph break ends the citation;
- code fences and code spans, HTML comments, and YAML front matter;
- a line carrying, or following,
  ``<!-- check-swallowed-citations: allow: <reason> -->``. The reason is
  required.

A finding is reported on the line holding the bracket, and it is in scope
when either that line or the cross-reference's line is one a diff adds.
The diff model (moved lines exempt, skip-not-fall-back) and the Markdown
masking come from ``check-write-idiom``, whose engine this script reuses.
Blocks by default (``CSC_FAIL`` defaults to true), because the defect is
silent in the render and the pattern has no legitimate use.

Configuration (environment variables, set by the composite action):
  CSC_BASE_REF, CSC_GLOBS, CSC_PATHS_IGNORE, CSC_FAIL, CSC_WHOLE_TREE
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
_DEFAULT_FAIL = True
# The reason after "allow:" is required.
ALLOW_RE = re.compile(r"<!--\s*check-swallowed-citations:\s*allow:\s*[^\s>-][^>]*-->")

# Quarto crossref prefixes.
CROSSREF_PREFIXES = (
    "fig tbl lst sec eq def thm lem cor prp cnj exm exr sol rem alg nte tip "
    "wrn imp cau apx ch".split()
)

# An in-text crossref: "@" not after a word character or "@" (so not an
# email), a known prefix, "-", then key characters ending in a word
# character, so trailing punctuation is not part of the key.
XREF_RE = re.compile(
    r"(?<![\w@])@(?P<ref>(?:" + "|".join(CROSSREF_PREFIXES) +
    r")-(?:[\w:.#$%&+?<>~/-]*\w)?)(?![\w:.#$%&+?<>~/-]*\w)"
)

# A bracket span with no nested brackets, not followed by "(", "[" or "{",
# which would make it a link, a reference link or a span.
BRACKET_RE = re.compile(r"\[[^\[\]]*\](?![(\[{])")
# A citation inside a bracket.
CITATION_IN_BRACKET_RE = re.compile(r"(?<![\w@])-?@[A-Za-z_]")

MESSAGE = (
    "@{ref} is followed by the citation {cite}, and Pandoc reads the pair as "
    "one citation, so {cite} drops out of the rendered page (lds#3239). "
    "Move the citation, or put a word or punctuation between the two, as in "
    '"@{ref}, following {cite}". '
    "Mark a deliberate use with <!-- check-swallowed-citations: allow: <reason> -->."
)


class Finding(NamedTuple):
    line: int
    ref_line: int
    ref: str
    cite: str


def _citation_brackets(masked: str) -> List[Tuple[int, int]]:
    """The spans of the brackets in ``masked`` that hold a citation."""
    return [(m.start(), m.end()) for m in BRACKET_RE.finditer(masked)
            if CITATION_IN_BRACKET_RE.search(m.group(0))]


def _leading_bracket(masked: str, brackets: List[Tuple[int, int]],
                     start: int) -> Optional[str]:
    """The citation bracket that follows ``start`` after only spaces, if any."""
    gap = len(masked) - len(masked[start:].lstrip(" \t"))
    for b_start, b_end in brackets:
        if b_start == gap:
            return masked[b_start:b_end]
    return None


def find_in_line(masked: str, pending: Optional[str]
                 ) -> Tuple[List[Tuple[str, str, bool]], Optional[str]]:
    """``([(ref, cite, on previous line), ...], ref left pending)`` for one
    masked line, given the crossref the previous line ended with."""
    found: List[Tuple[str, str, bool]] = []
    brackets = _citation_brackets(masked)
    if pending:
        cite = _leading_bracket(masked, brackets, 0)
        if cite:
            found.append((pending, cite, True))
    # A crossref inside a bracket, as in "[@eq-x] [@key]", is followed by
    # that bracket's "]", so it never reaches a citation bracket here.
    left: Optional[str] = None
    for hit in XREF_RE.finditer(masked):
        cite = _leading_bracket(masked, brackets, hit.end())
        if cite:
            found.append((hit.group("ref"), cite, False))
        elif not masked[hit.end():].strip():
            left = hit.group("ref")
    return found, left


def make_finder():
    """A per-file line checker that carries a crossref ending one line into
    the next line of the same paragraph."""
    pending: List[Optional[str]] = [None]

    def find(masked: str) -> List[Tuple[str, str, bool]]:
        found, pending[0] = find_in_line(masked, pending[0])
        return found

    return find


def scan_file(lines: List[str], keep: Optional[Set[int]] = None
              ) -> Tuple[List[Finding], int]:
    """``([Finding, ...], lines examined)``, kept when ``keep`` is None or
    holds the bracket's line or the crossref's line."""
    hits, examined = engine.scan_markdown(lines, make_finder(), ALLOW_RE)
    findings = []
    for number, (ref, cite, previous) in hits:
        finding = Finding(number, number - 1 if previous else number, ref, cite)
        if keep is None or finding.line in keep or finding.ref_line in keep:
            findings.append(finding)
    return findings, examined


# The engine passes the added-line set, so a finding is kept when either of
# its two lines is new.
scan_file.wants_scope = True  # type: ignore[attr-defined]


def format_message(finding: Finding) -> str:
    return MESSAGE.format(ref=finding.ref, cite=finding.cite)


def main() -> int:
    return engine.main(
        scan=scan_file, prefix="CSC_", name="swallowed-citations",
        clean="No citation is swallowed by a cross-reference before it.",
        summary="follow an in-text cross-reference with a citation that it swallows.",
        format_finding=format_message, default_fail=_DEFAULT_FAIL)


if __name__ == "__main__":
    sys.exit(main())
