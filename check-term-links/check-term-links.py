#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Flag a technical term whose first use in a passage is not linked to its definition.

The rule this enforces (Ezra, 2026-10-16; ai-config#4553, psw#223, psw#227): every
technical term is hyperlinked to its formal definition the first time it appears
in each div, or in each prose paragraph outside a div, and a term with no formal
definition gets one (gha#1078).

Which words are terms: the check learns them from the corpus itself.
1. Each `::: {#def-...}` div contributes its title (any heading inside it) and its
   bold terms, with parenthetical aliases ("also called" glosses) split out.
2. Each link whose target ends in `#def-...` contributes its link text, so a term
   defined on another site (`[risk](https://example.com/ch.html#def-risk)`) is known once
   anyone links it.
3. `--terms-file` adds terms by hand, one per line.
4. `--terms-dirs` names directories (space-separated) of prerequisite sites, such as
   checkouts of mds, pds and sds. Their `.qmd` files are read for the same def-div
   titles and bold terms, so a term defined there is known here, and its first use
   in each div must be linked (gha#1462). Those directories are never scanned for
   findings.

Findings:
- `unlinked-first-use`: the first occurrence of a known term in a passage is plain
  text, not inside a link or an `@def-...` cross-reference. The term's own def div
  is skipped, and so is any other passage in a div of a file that holds that def div.
- `partial-link`: a link covers only part of a longer defined phrase, such as
  "logistic [regression](#def-regression)" when "logistic regression" is defined.
  The whole phrase is the link (Ezra, 2026-10-24, lds#1375; gha#1219).
- `no-definition`: a bold term in a passage that is not a def div, and that
  matches no known term, so it is introduced as technical with no definition
  anywhere in the corpus. Give it a `#def-` div.

- `stale-allow`: a `check-term-links: allow` pragma on an added line that suppresses
  no finding. Delete it (gha#1771).
- `bare-allow`: an opt-out pragma on an added line with no reason. Write
  `<!-- check-term-links: allow: why this line is exempt -->` (gha#1772).

Skipped: code fences and spans, math, HTML comments, YAML front matter, include
shortcodes, headings, images, and the `(...)` of a link.

Opt-outs: `<!-- check-term-links: allow: reason -->` on a line skips that line
(a pragma with no reason still skips it but is reported as `bare-allow`);
`<!-- check-term-links: ignore-file -->` skips a file; `--allow-file` names terms
that are ordinary English in this corpus.

Scope: only a finding on a line a diff adds is reported (`--base-ref`, `--diff`),
so adopting the check does not reflag the corpus. An added line whose exact text
the same diff also deletes is moved, not new, so splitting a file reflags nothing;
so is a line, ignoring indentation and a list marker, that an unchanged line of
another file in the same directory holds, for a split that keeps the original.
`--whole-tree` reports every
finding, to measure a corpus. With no base and no `--whole-tree`, the check
skips with a warning rather than widening to the whole tree.
"""

import argparse
import fnmatch
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd"
DEFAULT_PATHS_IGNORE = ""

FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
DIV_OPEN_RE = re.compile(r"^(?P<fence>:{3,})\s*(?P<attrs>\{[^}]*\}|\S.*)?$")
DIV_CLOSE_RE = re.compile(r"^(?P<fence>:{3,})\s*$")
DEF_ID_RE = re.compile(r"#(?P<id>def-[A-Za-z0-9_-]+)")
HEADING_RE = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*(?:\{[^}]*\})?\s*$")
FILE_OPT_OUT_RE = re.compile(r"<!--\s*check-term-links:\s*ignore-file\s*-->", re.I)
LINE_OPT_OUT_RE = re.compile(
    r"<!--\s*check-term-links:\s*(?:allow|ignore)(?:\s*:(?:(?!-->).)*)?\s*-->", re.I
)
# The same pragma with nothing after `allow`: it gives no reason (gha#1772).
BARE_OPT_OUT_RE = re.compile(r"<!--\s*check-term-links:\s*(?:allow|ignore)(?:\s*:)?\s*-->", re.I)

COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
DISPLAY_MATH_RE = re.compile(r"\$\$.*?\$\$", re.S)
INLINE_MATH_RE = re.compile(r"(?<![\\$])\$(?!\s)(?:[^$\\\n]|\\.)+?(?<!\s)\$(?![\d$])")
SHORTCODE_RE = re.compile(r"\{\{<.*?>\}\}", re.S)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)(?:\{[^}]*\})?")
ATTR_RE = re.compile(r"\{[^{}\n]*\}")
CITATION_RE = re.compile(r"\[[^\[\]]*@[^\[\]]*\]")
# A bare URL, not the target of a `[text](url)` link, which the scan blanks after it finds the links.
URL_RE = re.compile(r"<https?://[^>]+>|(?<![(\[])https?://[^\s)]+")
LINK_TARGET_RE = re.compile(r"(?<=\])(?:\([^)]*\)|\[[^\]]*\])")
# [text](url) and [text][ref]; group "text" is what a reader clicks.
LINK_RE = re.compile(r"\[(?P<text>[^\[\]]+)\](?:\((?P<url>[^)\s]*)[^)]*\)|\[[^\]]*\])")
CROSSREF_RE = re.compile(r"@(?:def|thm|lem|cor|prp|cnj|exm|rem|sec)-[A-Za-z0-9_-]+")
FOLLOWING_CROSSREF_RE = re.compile(r"(?:\*\*|__)?\s*\(\s*@def-[A-Za-z0-9_-]+\s*\)")
BOLD_RE =re.compile(r"\*\*(?P<term>[^*\n]+?)\*\*|__(?P<term2>[^_\n]+?)__")

COMMON_LABELS = frozenset({
    "note", "warning", "caution", "tip", "important", "example", "remark",
    "definition", "step", "case", "proof", "solution", "answer", "question",
    "summary", "recap", "prerequisite", "prerequisites", "todo", "fixme",
    "exercise", "hint", "why", "how", "what", "when", "where", "goal",
    "source", "sources", "reference", "references",
})
# Bold used for emphasis on a function word, which no definition div would cover.
EMPHASIS_WORDS = frozenset({
    "not", "once", "and", "or", "if", "then", "all", "any", "each", "every", "only",
    "both", "either", "neither", "never", "always", "must", "cannot", "can", "does",
    "same", "different", "before", "after", "twice", "exactly", "nothing", "none",
    "before", "without", "with", "than", "more", "less", "most", "least", "one",
    "two", "three", "first", "second", "third", "last", "next", "also", "too",
})
# Words that are never a term to link, however a prerequisite site tags them
# (gha#1488): logic definitions carry aliases such as "and" and "not", and
# `#def-` links wrap words such as "number".  A project adds more through
# `allow-file`.
FUNCTION_WORDS = frozenset({
    "the", "an", "and", "but", "nor", "for", "yet", "not", "that", "this", "these",
    "those", "there", "here", "when", "where", "while", "which", "who", "whom",
    "what", "why", "how", "from", "into", "onto", "upon", "over", "under", "than",
    "such", "some", "other", "another", "are", "was", "were", "been", "being", "has",
    "have", "had", "did", "will", "would", "should", "could", "may", "might", "its",
    "their", "them", "they", "our", "you", "your", "his", "her", "she", "also", "just",
    # Connectives and task verbs that a prerequisite site may tag as an alias (gha#1498).
    "therefore", "thus", "hence", "because", "since", "so", "let", "compute", "computes",
    "computed", "computing", "use", "uses", "used", "using", "given", "gives", "give",
})
GENERIC_NOUNS = frozenset({"number", "numbers", "value", "values"})
LEADING_ARTICLE_RE =re.compile(r"^(?:the|a|an)\s+", re.I)
MIN_TERM_LEN = 3
MAX_TERM_WORDS = 5


@dataclass(frozen=True)
class Finding:
    file: Path
    line: int
    rule: str
    term: str
    message: str


@dataclass
class Passage:
    """Consecutive prose lines that form one 'first use' scope."""

    div_id: Optional[str]
    in_div: bool
    lines: List[Tuple[int, str]]  # (1-based line number, masked text)
    attrs: str = ""  # the attributes of every div the passage sits in


# A div that carries its own argument: an exercise, a solution, a result or a proof reads on its own,
# so a term it uses is linked in it even when its file also holds the term's definition (gha#1316, gha#1539).
WORKED_DIV_RE = re.compile(
    r"#(?:exm|exr|sol|thm|lem|cor|prp|cnj|prf|rem(?!-source))-|\.(?:sol|solution|proof|exercise)\b"
)


def is_worked_div(attrs: str) -> bool:
    """True for an exercise, solution, result, proof or remark div, not a source callout."""
    return WORKED_DIV_RE.search(attrs) is not None


def term_key(term: str) -> str:
    """Normalize a term for lookup: lowercase, articles dropped, runs of space and hyphen folded."""
    t = LEADING_ARTICLE_RE.sub("", term.strip().strip("*_\"'“”‘’").strip())
    t = re.sub(r"[\s\-\u2010-\u2015]+", " ", t).lower()
    return t


def plural_forms(word: str) -> Set[str]:
    """The singular `word` and the plural and possessive forms a reader meets (gha#1630).

    Covers regular `s`/`es`, `y` -> `ies` (entropy, entropies), `ix`/`ex` -> `ices`
    (matrix, matrices), `is` -> `es` (hypothesis, hypotheses), `um`/`on` -> `a`
    (maximum, maxima; criterion, criteria) and `f`/`fe` -> `ves` (half, halves).
    """
    forms = {word, word + "s", word + "es"}
    if word.endswith("y") and len(word) > 2 and word[-2] not in "aeiou":
        forms.add(word[:-1] + "ies")
    if word.endswith(("ix", "ex")):
        forms.add(word[:-2] + "ices")
    if word.endswith("is"):
        forms.add(word[:-2] + "es")
    if word.endswith(("um", "on")):
        forms.add(word[:-2] + "a")
    if word.endswith("fe"):
        forms.add(word[:-2] + "ves")
    elif word.endswith("f"):
        forms.add(word[:-1] + "ves")
    return forms


def singular_candidates(word: str) -> List[str]:
    """Every singular `word` could be the plural of, for a dictionary lookup."""
    out = [word]
    if word.endswith("ies"):
        out.append(word[:-3] + "y")
    if word.endswith("ices"):
        out += [word[:-4] + "ix", word[:-4] + "ex"]
    if word.endswith("ves"):
        out += [word[:-3] + "f", word[:-3] + "fe"]
    if word.endswith("es"):
        out += [word[:-2], word[:-2] + "is"]
    if word.endswith("a"):
        out += [word[:-1] + "um", word[:-1] + "on"]
    if word.endswith("s"):
        out.append(word[:-1])
    return out


def lookup(text: str, terms: Dict[str, Set[str]]) -> Optional[str]:
    """The key of the known term `text` names, allowing an inflected last word, or None."""
    key = term_key(text)
    head, _, last = key.rpartition(" ")
    # The singular wins over a plural that a link text also made a term, so a
    # linked "probability" covers "probabilities" in the same div.
    for cand in [*singular_candidates(last)[1:], last]:
        full = f"{head} {cand}" if head else cand
        if full in terms:
            return full
    return None


def usable_term(term: str, allowed_out: Set[str]) -> bool:
    key = term_key(term)
    if len(key) < MIN_TERM_LEN or len(key.split()) > MAX_TERM_WORDS:
        return False
    if key in COMMON_LABELS or key in FUNCTION_WORDS or key in EMPHASIS_WORDS:
        return False
    if key in GENERIC_NOUNS or key in allowed_out:
        return False
    # Words only: a term with math, a colon or other markup is not a prose term.
    return re.fullmatch(r"[^\W\d_][\w' ]*", key) is not None


def mask_inline(text: str) -> str:
    """Blank spans that are not prose, keeping every offset and newline in place."""

    def blank(m: "re.Match[str]") -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    for rx in (COMMENT_RE, DISPLAY_MATH_RE, INLINE_CODE_RE, INLINE_MATH_RE,
               SHORTCODE_RE, IMAGE_RE, URL_RE):
        text = rx.sub(blank, text)
    # `ATTR_RE` last: `{...}` after a link or a header is markup, never prose.
    return ATTR_RE.sub(blank, text)


def preprocess(lines: Sequence[str]) -> Tuple[List[str], Set[int]]:
    """Return each line with front matter, code fences and comments blanked, and the opted-out line numbers."""
    out: List[str] = []
    opted: Set[int] = set()
    in_yaml = False
    fence = ""
    in_comment = False
    for idx, raw in enumerate(lines, start=1):
        if idx == 1 and raw.strip() == "---":
            in_yaml = True
            out.append("")
            continue
        if in_yaml:
            in_yaml = raw.strip() not in ("---", "...")
            out.append("")
            continue
        m = FENCE_RE.match(raw)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = ""
            out.append("")
            continue
        if m and not in_comment:
            fence = m.group(1)
            out.append("")
            continue
        if LINE_OPT_OUT_RE.search(raw):
            opted.add(idx)
        line = raw
        if in_comment:
            end = line.find("-->")
            if end == -1:
                out.append("")
                continue
            line = " " * (end + 3) + line[end + 3:]
            in_comment = False
        # Drop closed comments, then an unterminated one that runs to the end of the line.
        line = COMMENT_RE.sub(lambda mm: " " * len(mm.group(0)), line)
        start = line.find("<!--")
        if start != -1:
            line = line[:start]
            in_comment = True
        out.append(line)
    return out, opted


def split_passages(masked: Sequence[str]) -> List[Passage]:
    """Cut a file into passages: one per div (between div fences), one per paragraph outside divs."""
    passages: List[Passage] = []
    stack: List[Tuple[int, Optional[str]]] = []  # (fence length, def id or None)
    attrs_stack: List[str] = []
    cur: List[Tuple[int, str]] = []

    def flush() -> None:
        nonlocal cur
        if cur:
            div_id = next((d for _, d in reversed(stack) if d), None) if stack else None
            passages.append(Passage(
                div_id=div_id, in_div=bool(stack), lines=cur, attrs=" ".join(attrs_stack),
            ))
        cur = []

    for idx, line in enumerate(masked, start=1):
        s = line.strip()
        m_close = DIV_CLOSE_RE.match(s)
        m_open = None if m_close else DIV_OPEN_RE.match(s)
        if m_open:
            flush()
            attrs = m_open.group("attrs") or ""
            d = DEF_ID_RE.search(attrs)
            stack.append((len(m_open.group("fence")), d.group("id") if d else None))
            attrs_stack.append(attrs)
            continue
        if m_close:
            flush()
            if stack and len(m_close.group("fence")) >= stack[-1][0]:
                stack.pop()
                attrs_stack.pop()
            continue
        if HEADING_RE.match(s):
            flush()
            continue
        if not s and not stack:
            flush()
            continue
        if s:
            cur.append((idx, line))
    flush()
    return passages


def harvest_terms(
    masked: Sequence[str], allowed_out: Set[str]
) -> Dict[str, Set[str]]:
    """Map term key -> def ids it defines, from def-div titles and bold terms, and from links to `#def-` anchors."""
    terms: Dict[str, Set[str]] = {}

    # Words of the multi-word terms each def div defines.  A one-word alias made of one of
    # them, such as "positive" for "positive classification", is an ordinary adjective
    # elsewhere, so it is not learned (gha#1635).
    multiword: Dict[str, Set[str]] = {}

    def add(term: str, def_id: str, from_link: bool = False) -> None:
        parts = re.split(r"\s*(,|;|\bor\b|\balso called\b|\bknown as\b)\s*", term)
        for i in range(0, len(parts), 2):
            piece = parts[i]
            listed = i > 0 and parts[i - 1] in {",", ";", "or"}  # a plainly listed alias
            aliases = re.findall(r"\(([^)]*)\)", piece)
            piece = re.sub(r"\([^)]*\)", "", piece).strip()
            for candidate in [piece, *aliases]:
                if not usable_term(candidate, allowed_out):
                    continue
                key = term_key(candidate)
                if " " in key:
                    multiword.setdefault(def_id, set()).update(key.split())
                elif not (from_link or listed) and key in multiword.get(def_id, ()):
                    continue
                terms.setdefault(key, set()).add(def_id)

    stack: List[Tuple[int, Optional[str]]] = []
    for line in masked:
        s = line.strip()
        m_close = DIV_CLOSE_RE.match(s)
        m_open = None if m_close else DIV_OPEN_RE.match(s)
        if m_open:
            d = DEF_ID_RE.search(m_open.group("attrs") or "")
            stack.append((len(m_open.group("fence")), d.group("id") if d else None))
            continue
        if m_close:
            if stack and len(m_close.group("fence")) >= stack[-1][0]:
                stack.pop()
            continue
        def_id = next((d for _, d in reversed(stack) if d), None)
        if def_id:
            h = HEADING_RE.match(s)
            if h:
                add(mask_inline(h.group("title")), def_id)
            else:
                for b in BOLD_RE.finditer(mask_inline(line)):
                    add(b.group("term") or b.group("term2"), def_id)
        for lm in LINK_RE.finditer(mask_inline(line)):
            url = lm.group("url") or ""
            frag = re.search(r"#(def-[A-Za-z0-9_-]+)$", url)
            if frag:
                add(lm.group("text"), frag.group(1), from_link=True)
    return terms


def term_regex(keys: Sequence[str]) -> "re.Pattern[str]":
    """One alternation, longest term first, matching a term's inflected last word and flexible spacing."""
    parts = []
    for key in sorted(keys, key=len, reverse=True):
        words = key.split()
        escaped = [re.escape(w) for w in words[:-1]]
        forms = sorted(plural_forms(words[-1]), key=len, reverse=True)
        escaped.append("(?:" + "|".join(re.escape(f) for f in forms) + ")")
        parts.append(r"[\s\-\u2010-\u2015]+".join(escaped))
    return re.compile(
        r"(?<![\w\-])(?:" + "|".join(parts) + r")(?![\w\-])", re.I
    )


def scan_passage(
    path: Path,
    passage: Passage,
    terms: Dict[str, Set[str]],
    rx: Optional["re.Pattern[str]"],
    opted: Set[int],
    added: Optional[Set[int]],
    own_defs: Optional[Set[str]] = None,
    used_optouts: Optional[Set[int]] = None,
) -> List[Finding]:
    findings: List[Finding] = []
    line_of: List[int] = []  # offset -> 1-based line number
    chunks: List[str] = []
    for n, text in passage.lines:
        chunks.append(text + "\n")
        line_of.extend([n] * (len(text) + 1))
    text = mask_inline("".join(chunks))

    def line_at(offset: int) -> int:
        return line_of[min(offset, len(line_of) - 1)]

    # A citation `[@key]` and a crossref are not prose; the crossref also counts as a link.
    link_spans = [m.span() for m in LINK_RE.finditer(text)]
    link_spans += [m.span() for m in CROSSREF_RE.finditer(text)]
    prose = CITATION_RE.sub(lambda m: " " * len(m.group(0)), text)
    prose = LINK_TARGET_RE.sub(lambda m: " " * len(m.group(0)), prose)
    # Blank a link's brackets (keeping offsets) so a phrase split by a link still matches whole.
    chars = list(prose)
    for lm in LINK_RE.finditer(text):
        chars[lm.start()] = " "
        chars[lm.start() + 1 + len(lm.group("text"))] = " "
    prose = "".join(chars)

    def reportable(n: int) -> bool:
        if n in opted:
            # The pragma on this line suppressed a finding, so it is not stale.
            if used_optouts is not None:
                used_optouts.add(n)
            return False
        return added is None or n in added

    seen: Set[str] = set()
    if rx is not None:
        for m in rx.finditer(prose):
            key = lookup(m.group(0), terms)
            if key is None:
                continue
            if key in seen:
                continue
            seen.add(key)
            if passage.div_id and passage.div_id in terms[key]:
                continue
            # A div beside the def div in the same file (a source callout) is part of that definition; prose outside divs is still checked.
            if passage.in_div and own_defs and terms[key] & own_defs and not is_worked_div(passage.attrs):
                continue
            start = m.start()
            if any(a <= start and m.end() <= b for a, b in link_spans):
                continue
            # A link over only part of a longer defined term: the whole phrase is the link.
            if any(a < m.end() and start < b for a, b in link_spans):
                n = line_at(start)
                if reportable(n):
                    findings.append(Finding(
                        file=path, line=n, rule="partial-link", term=key,
                        message=(
                            f"'{m.group(0)}' is a defined phrase; link the whole "
                            "phrase to its definition, not a shorter term inside it."
                        ),
                    ))
                continue
            # "term (@def-term)" links the term it follows.
            if FOLLOWING_CROSSREF_RE.match(prose, m.end()):
                continue
            n = line_at(start)
            if not reportable(n):
                continue
            findings.append(Finding(
                file=path, line=n, rule="unlinked-first-use", term=key,
                message=(
                    f"'{m.group(0)}' is a defined term; link its first use in this "
                    f"{'div' if passage.in_div else 'paragraph'} to its definition."
                ),
            ))

    # A bold term in a non-def passage that no def anywhere covers.
    if not (passage.div_id and passage.div_id.startswith("def-")):
        for b in BOLD_RE.finditer(prose):
            term = b.group("term") or b.group("term2")
            end = b.end()
            if prose[end:end + 1] == ":" or not usable_term(term, EMPHASIS_WORDS):
                continue
            key = term_key(term)
            if lookup(term, terms) is not None:
                continue
            n = line_at(b.start())
            if not reportable(n):
                continue
            findings.append(Finding(
                file=path, line=n, rule="no-definition", term=key,
                message=(
                    f"Bold term '{term.strip()}' has no definition div anywhere in "
                    "the corpus; give it a `#def-` div and link to it."
                ),
            ))
    return findings


def scan_file(
    path: Path,
    lines: Sequence[str],
    terms: Dict[str, Set[str]],
    rx: Optional["re.Pattern[str]"],
    added: Optional[Set[int]],
) -> List[Finding]:
    if FILE_OPT_OUT_RE.search("\n".join(lines)):
        return []
    masked, opted = preprocess(lines)
    findings: List[Finding] = []
    passages = split_passages(masked)
    own_defs = {p.div_id for p in passages if p.div_id}
    used_optouts: Set[int] = set()
    for passage in passages:
        findings.extend(scan_passage(path, passage, terms, rx, opted, added, own_defs, used_optouts))
    for n in sorted(opted):
        if (added is None or n in added) and BARE_OPT_OUT_RE.search(lines[n - 1]):
            findings.append(Finding(
                file=path, line=n, rule="bare-allow", term="",
                message=(
                    "This check-term-links opt-out pragma gives no reason; write "
                    "`<!-- check-term-links: allow: <why this line is exempt> -->`."
                ),
            ))
    # A pragma that suppresses nothing is dead weight, and being line-wide it would hide
    # the next finding on that line (gha#1771).
    for n in sorted(opted - used_optouts):
        if added is None or n in added:
            findings.append(Finding(
                file=path, line=n, rule="stale-allow", term="",
                message="This check-term-links opt-out pragma suppresses no finding on its line; delete it.",
            ))
    return sorted(findings, key=lambda f: (f.line, f.rule, f.term))


def parse_added_lines(diff_text: str, repo_root: Path) -> Dict[Path, Set[int]]:
    """Added line numbers per file from a `git diff -U0` text.

    An added line whose exact text (ignoring surrounding whitespace) the same
    diff also deletes is moved, not new, and is left out, so splitting a file
    does not reflag the first uses it already carried.
    """
    added: Dict[Path, Dict[int, str]] = {}
    deleted: Set[str] = set()
    current: Optional[Path] = None
    new_n = old_left = new_left = 0
    for line in diff_text.splitlines():
        # Hunk counts say how many body lines follow, so a body line that
        # starts with "++" or "--" is never read as a file header.
        if line.startswith("+") and new_left > 0 and current is not None:
            added[current][new_n] = line[1:].strip()
            new_n += 1
            new_left -= 1
        elif line.startswith("-") and old_left > 0:
            deleted.add(line[1:].strip())
            old_left -= 1
        elif line.startswith("+++ b/"):
            current = repo_root / line[6:].strip()
            added.setdefault(current, {})
        elif line.startswith("@@ ") and current is not None:
            m = re.match(r"@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                old_left = int(m.group(1)) if m.group(1) is not None else 1
                new_n = int(m.group(2))
                new_left = int(m.group(3)) if m.group(3) is not None else 1
    return {
        f: {n for n, text in lines.items() if not text or text not in deleted}
        for f, lines in added.items()
    }


def diff_added_lines(
    base_ref: str, repo_root: Path, globs: Sequence[str]
) -> Optional[Dict[Path, Set[int]]]:
    """Lines added between the merge base with `base_ref` and the working tree, or None if git cannot say."""
    mb = subprocess.run(
        ["git", "merge-base", base_ref, "HEAD"], cwd=repo_root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if mb.returncode != 0 or not mb.stdout.strip():
        return None
    diff = subprocess.run(
        ["git", "diff", "-U0", mb.stdout.strip(), "--", *globs], cwd=repo_root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if diff.returncode != 0:
        return None
    return drop_sibling_moves(parse_added_lines(diff.stdout, repo_root))


LIST_MARKER_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s+")


def moved_key(text: str) -> str:
    """A line's text with surrounding whitespace and a list marker removed."""
    return LIST_MARKER_RE.sub("", text.strip())


def file_lines(path: Path) -> List[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").split("\n")
    except OSError:
        return []


def drop_sibling_moves(added: Dict[Path, Set[int]]) -> Dict[Path, Set[int]]:
    """Drop an added line whose text an unchanged line of a sibling file holds.

    A split that keeps the original file deletes nothing, so the exact-deletion
    test misses it (gha#1792). A line counts as moved when, with its list
    marker and indentation removed, it equals a line of another file in the same
    directory that the diff does not add; lines the deletion test already
    dropped count as not added here too.
    """
    unchanged: Dict[Path, Set[str]] = {}
    for path in added:
        for sib in path.parent.glob("*" + path.suffix):
            if sib not in unchanged:
                skip = added.get(sib, set())
                unchanged[sib] = {
                    moved_key(t) for n, t in enumerate(file_lines(sib), start=1)
                    if n not in skip and t.strip()
                }
    out: Dict[Path, Set[int]] = {}
    for path, numbers in added.items():
        lines = file_lines(path)
        others: Set[str] = set()
        for sib, keys in unchanged.items():
            if sib != path and sib.parent == path.parent and sib.suffix == path.suffix:
                others |= keys
        out[path] = {
            n for n in numbers
            if not (0 < n <= len(lines) and lines[n - 1].strip()
                    and moved_key(lines[n - 1]) in others)
        }
    return out


def glob_to_regex(pat: str) -> "re.Pattern[str]":
    pat = pat.strip().strip("/")
    out = ""
    i = 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pat.startswith("**", i):
            out += ".*"
            i += 2
        elif pat[i] == "*":
            out += "[^/]*"
            i += 1
        elif pat[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pat[i])
            i += 1
    return re.compile(r"^" + out + r"(?:/.*)?$")


def read_term_list(path: str) -> Set[str]:
    """Keys from a one-term-per-line file; blank lines and `#` comments are skipped."""
    if not path:
        return set()
    p = Path(path)
    if not p.is_file():
        print(f"::warning::check-term-links: terms/allow file '{path}' not found.", file=sys.stderr)
        return set()
    keys = set()
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        t = raw.split("#", 1)[0].strip()
        if t:
            keys.add(term_key(t))
    return keys


def harvest_dirs(dirs: Sequence[str], allowed_out: Set[str]) -> Dict[str, Set[str]]:
    """Terms defined by the `.qmd` files under each directory of a prerequisite site.

    The def ids are dropped: they name divs in another repository, so they must
    not exempt a passage here (the own-def exemption compares ids).
    """
    terms: Dict[str, Set[str]] = {}
    for d in dirs:
        base = Path(d)
        if not base.is_dir():
            print(f"::warning::check-term-links: terms directory '{d}' not found.", file=sys.stderr)
            continue
        for f in sorted(base.rglob("*.qmd")):
            if ".git" in f.parts or ".quarto" in f.parts:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            if FILE_OPT_OUT_RE.search(text):
                continue
            masked, _ = preprocess(text.splitlines())
            for k in harvest_terms(masked, allowed_out):
                terms.setdefault(k, set())
    return terms


def tracked_files(root: Path, globs: Sequence[str]) -> List[Path]:
    res = subprocess.run(
        ["git", "ls-files", "-z", "--", *globs], cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if res.returncode == 0:
        return [
            (root / raw.decode("utf-8", "replace")).resolve()
            for raw in res.stdout.split(b"\0") if raw
        ]
    return [p.resolve() for g in globs for p in root.rglob(g) if p.is_file()]


def truthy(value: str) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes")


def main() -> int:
    env = os.environ.get
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--globs", default=env("TERM_LINKS_GLOBS", DEFAULT_GLOBS))
    ap.add_argument("--paths-ignore", default=env("TERM_LINKS_PATHS_IGNORE", DEFAULT_PATHS_IGNORE))
    ap.add_argument("--terms-file", default=env("TERM_LINKS_TERMS_FILE", ""))
    ap.add_argument("--terms-dirs", default=env("TERM_LINKS_TERMS_DIRS", ""))
    ap.add_argument("--allow-file", default=env("TERM_LINKS_ALLOW_FILE", ""))
    ap.add_argument("--base-ref", default=env("TERM_LINKS_BASE_REF", ""))
    ap.add_argument("--diff", default=env("TERM_LINKS_DIFF_FILE", ""))
    ap.add_argument("--whole-tree", default=env("TERM_LINKS_WHOLE_TREE", "false"))
    ap.add_argument("--fail", default=env("TERM_LINKS_FAIL", "true"))
    args = ap.parse_args()

    root = Path.cwd()
    globs = args.globs.split()
    ignores = [glob_to_regex(p) for p in re.split(r"[,\n]+", args.paths_ignore) if p.strip()]
    should_fail = truthy(args.fail)

    files = [
        f for f in sorted(set(tracked_files(root, globs)))
        if not any(rx.match(str(f.relative_to(root)).replace("\\", "/")) for rx in ignores)
    ]

    added_map: Optional[Dict[Path, Set[int]]] = None
    if not truthy(args.whole_tree):
        if args.diff.strip() and Path(args.diff).is_file():
            added_map = parse_added_lines(
                Path(args.diff).read_text(encoding="utf-8", errors="replace"), root
            )
        elif args.base_ref.strip():
            added_map = diff_added_lines(args.base_ref.strip(), root, globs)
        if added_map is None:
            print(
                "::warning::check-term-links: no base-ref or diff to scope to (or git "
                "could not compute it); skipping rather than reflagging the whole tree. "
                "Pass whole-tree: true to scan everything.",
                file=sys.stderr,
            )
            return 0

    allowed_out = read_term_list(args.allow_file)
    contents: Dict[Path, List[str]] = {}
    terms: Dict[str, Set[str]] = {}
    for f in files:
        try:
            contents[f] = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            print(f"Warning: could not read {f}: {exc}", file=sys.stderr)
            continue
        masked, _ = preprocess(contents[f])
        if FILE_OPT_OUT_RE.search("\n".join(contents[f])):
            continue
        for k, ids in harvest_terms(masked, allowed_out).items():
            terms.setdefault(k, set()).update(ids)
    for k in read_term_list(args.terms_file):
        if usable_term(k, allowed_out):
            terms.setdefault(k, set())
    for k in harvest_dirs(args.terms_dirs.split(), allowed_out):
        terms.setdefault(k, set())
    rx = term_regex(list(terms)) if terms else None

    findings: List[Finding] = []
    for f, lines in contents.items():
        added = added_map.get(f) if added_map is not None else None
        if added_map is not None and not added:
            continue
        findings.extend(scan_file(f, lines, terms, rx, added))

    severity = "error" if should_fail else "warning"
    if findings:
        print(f"check-term-links: {len(findings)} finding(s); {len(terms)} known term(s).\n")
        for fd in findings:
            rel = str(fd.file.relative_to(root)).replace("\\", "/")
            print(f"  {rel}:{fd.line}: [{fd.rule}] {fd.message}")
            print(f"::{severity} file={rel},line={fd.line},title=Term link::[{fd.rule}] {fd.message}")
    else:
        print(f"check-term-links: Clean ({len(terms)} known term(s), {len(files)} file(s)).")
    return 1 if findings and should_fail else 0


if __name__ == "__main__":
    sys.exit(main())
