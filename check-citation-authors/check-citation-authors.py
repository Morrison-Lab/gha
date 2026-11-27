#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag an author's surname typed next to a citation of that author's work.

The rule is psw's "Let the citation name the source" (Morrison-Lab/psw#679,
Morrison-Lab/gha#2144): an in-text ``@key`` already prints the author names,
so a sentence should not type them again beside the citation.

- Flagged: ``The figure follows the layout of a figure in James et al.
  [@james2021islr, Figure 6.7].``
- Preferred: ``The figure follows the layout of @james2021islr [Figure 6.7].``

What is flagged: in ``.qmd`` and ``.md`` files, a capitalized word within
``WINDOW`` words before a citation key (``[@key``, ``[see @key``,
``(@key``, or a bare ``@key``), when the key starts with that word in lower
case, so ``James`` and ``@james2021islr``. A lowercase particle before the
word joins it (``van Buuren`` and ``@vanbuuren2018``), a possessive ``'s``
is dropped (``Gauss's`` and ``@gauss1809``), and accents are folded. The
key-prefix match keeps false positives low, since lab bib keys start with
the first author's surname. The window may reach back onto the previous
line of the same paragraph, since the notes break lines at clauses, and it
stops at the end of the previous sentence.

What is not flagged:

- ``James et al. [-@james2021islr]``: the minus suppresses the author, so
  the typed name is the only one printed;
- a name inside link text or emphasis, where it is part of a term or a
  title: ``[Cook's distance](#def-x) [@cook1977]``,
  ``**Cox proportional hazards** [@cox1972]``;
- a crossref such as ``@fig-x`` or ``@sec-y``, and an email address;
- a word of one letter, or a word that is not capitalized;
- code fences and code spans, HTML comments, and YAML front matter;
- a line carrying, or following,
  ``<!-- check-citation-authors: allow: <reason> -->``. The reason is
  required, as in ``allow: names one author of a multi-author source``.

The diff model (added lines only, moved lines exempt, skip-not-fall-back)
and the Markdown masking come from ``check-write-idiom``, whose engine this
script reuses. Warn-only by default (``CCA_FAIL`` defaults to false) while
the false-positive rate is measured, as gha#2144 asks.

Configuration (environment variables, set by the composite action):
  CCA_BASE_REF, CCA_GLOBS, CCA_PATHS_IGNORE, CCA_FAIL, CCA_WHOLE_TREE
as for ``check-write-idiom`` (see its docstring).
"""

import importlib.util
import re
import sys
import unicodedata
from pathlib import Path
from typing import Callable, List, NamedTuple, Optional, Tuple

_ENGINE_PATH = Path(__file__).resolve().parent.parent / "check-write-idiom" / "check-write-idiom.py"
_spec = importlib.util.spec_from_file_location("check_write_idiom_engine", _ENGINE_PATH)
assert _spec is not None and _spec.loader is not None
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)

DEFAULT_GLOBS = engine.DEFAULT_GLOBS
_DEFAULT_FAIL = False
# The reason after "allow:" is required.
ALLOW_RE = re.compile(r"<!--\s*check-citation-authors:\s*allow:\s*[^\s>-][^>]*-->")

# How many words before a citation key are read.
WINDOW = 6

# A Pandoc citation key: "@" not after a word character (so not an email),
# then a letter or underscore, then key characters. A key may hold internal
# punctuation ":.#$%&-+?<>~/", but not end with it.
CITE_RE = re.compile(r"(?<![\w@])(?P<minus>-?)@(?P<key>[A-Za-z_][\w:.#$%&+?<>~/-]*\w|[A-Za-z_])")

# Quarto crossref prefixes; a key starting "<prefix>-" is a crossref, not a citation.
CROSSREF_PREFIXES = frozenset(
    "fig tbl lst sec eq def thm lem cor prp cnj exm exr sol rem alg nte tip "
    "wrn imp cau apx ch".split()
)

WORD_RE = re.compile(r"[^\W\d_][\w'’-]*")
PARTICLES = frozenset(
    "van von de der den del della di da du la le ten ter st".split()
)

# The end of the previous sentence: terminal punctuation, optional closers,
# then whitespace. "et al." and an initial ("J. Smith") do not end one.
SENTENCE_END_RE = re.compile(r"(?<!\bal)(?<!\b[A-Z])[.!?][\"')\]”’*_]*\s+")

# Link text with its target, strong emphasis, and emphasis.
LINK_RE = re.compile(r"\[[^\[\]]*\]\([^()]*\)")
STRONG_RE = re.compile(r"(\*\*|__)(?=\S).+?(?<=\S)\1")
EMPH_RE = re.compile(r"(?<![\w*])([*_])(?=\S)[^*_]+?(?<=\S)\1(?![\w*])")

MESSAGE = (
    'typed "{word}" next to @{key}, which already prints the author names; '
    "let the citation name the source, as in "
    '"@{key} [Figure 6.7]" rather than "{word} et al. [@{key}, Figure 6.7]", '
    "or suppress the printed name with [-@{key}] "
    '(psw "Let the citation name the source", gha#2144). '
    "Mark a deliberate use with <!-- check-citation-authors: allow: <reason> -->."
)


class Finding(NamedTuple):
    line: int
    word: str
    key: str


def _fold(word: str) -> str:
    """Lower-case letters only, accents folded and a possessive dropped."""
    word = re.sub(r"['’]s?$", "", word)
    decomposed = unicodedata.normalize("NFKD", word)
    return "".join(c for c in decomposed if c.isalpha()).casefold()


def _is_crossref(key: str) -> bool:
    head, dash, _ = key.partition("-")
    return bool(dash) and head.lower() in CROSSREF_PREFIXES


def _current_sentence(text: str) -> str:
    """The part of ``text`` after the last sentence end in it."""
    ends = list(SENTENCE_END_RE.finditer(text))
    return text[ends[-1].end():] if ends else text


def _mask_terms(text: str) -> str:
    """Blank link text and emphasis, where a name is part of a term or a
    title rather than a typed credit: ``[Cook's distance](#def-x)``,
    ``**Cox proportional hazards**``, ``*Practical R for Epidemiologists*``."""
    blank = lambda m: " " * len(m.group(0))  # noqa: E731
    for pattern in (LINK_RE, STRONG_RE, EMPH_RE):
        text = pattern.sub(blank, text)
    return text


def _named_author(before: str, key: str) -> Optional[str]:
    """The capitalized word among the last ``WINDOW`` words of ``before`` that
    ``key`` starts with, joined to any particles before it, or None."""
    words = WORD_RE.findall(_mask_terms(_current_sentence(before)))[-WINDOW:]
    folded_key = _fold(key)
    for i, word in enumerate(words):
        if not word[0].isupper():
            continue
        name = word
        j = i
        while j > 0 and words[j - 1] in PARTICLES:
            j -= 1
            name = words[j] + " " + name
        stem = _fold(name.replace(" ", ""))
        if len(stem) >= 2 and folded_key.startswith(stem):
            return name
    return None


def make_finder() -> Callable[[str], List[Tuple[str, str]]]:
    """A per-file line checker that remembers the previous line of the
    paragraph, so a name at the end of one line and a citation at the start
    of the next are read together."""
    previous = [""]

    def find(masked: str) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        start = 0
        for hit in CITE_RE.finditer(masked):
            key = hit.group("key")
            if hit.group("minus") or _is_crossref(key):
                start = hit.end()
                continue
            # Read back to the previous citation on this line, or onto the
            # previous line when this is the first.
            before = masked[start:hit.start()]
            if start == 0 and previous[0]:
                before = previous[0] + " " + before
            word = _named_author(before, key)
            if word:
                out.append((word, key))
            start = hit.end()
        previous[0] = masked if masked.strip() else ""
        return out

    return find


def scan_file(lines: List[str]) -> Tuple[List[Finding], int]:
    """``([Finding, ...], lines examined)`` for a Markdown-family file."""
    hits, examined = engine.scan_markdown(lines, make_finder(), ALLOW_RE)
    return [Finding(number, word, key) for number, (word, key) in hits], examined


def format_message(finding: Finding) -> str:
    return MESSAGE.format(word=finding.word, key=finding.key)


def main() -> int:
    return engine.main(
        scan=scan_file, prefix="CCA_", name="citation-authors",
        clean="No author name typed next to a citation of the same source.",
        summary="type an author name next to a citation that already prints it.",
        format_finding=format_message, default_fail=_DEFAULT_FAIL)


if __name__ == "__main__":
    sys.exit(main())
