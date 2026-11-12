#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Flag informal definitions written in running prose instead of Quarto def divs.

The rule this enforces: in content repositories (Quarto books and sites that use
theorem-type cross-reference divs), technical concepts must be formally defined
in dedicated theorem-like definition divs (`::: {#def-...}`), never in running
prose (gha#970, ai-config shared/writing/informal-definitions.md).

Concepts defined only in prose lack stable cross-reference IDs, cannot be cited
downstream, break hyperlink-on-first-mention requirements, and escape consistency
audits.

This check flags:
1. Bolded or emphasized terms followed by defining language ("is", "are",
   "means", "refers to", "is defined as", "\\eqdef", "\\triangleq") outside a
   formal `::: {#def-...}` (or sibling theorem) div.
2. `\\eqdef` or `\\triangleq` used in inline or display math outside a def div.
3. Prose paragraphs or bolded terms directly under a heading titled "Definitions"
   that are not wrapped in formal def divs.
4. Naming sentences ending in "is:" or "are:" immediately preceding display math
   (`$$...$$`) outside a def div.
5. A `::: {#def-...}` div that defines more than one term: more than one bold
   term in its own prose that is not introduced as an alias ("also called",
   "or", "known as"). One definition per div.
6. A `::: {#def-...}` div with prose and no hyperlink or cross-reference
   (`no-link-in-definition`): every technical term is linked on first use in
   each div (ai-config#4600). Warn-only like the rest; `allow` opts out.

Opt-out directives:
- Line/block level: `<!-- check-informal-definitions: allow -->` or
  `<!-- check-informal-definitions: ignore -->`
- File level: `<!-- check-informal-definitions: ignore-file -->`

Sections titled "Notation", "Typographic Conventions", or "Symbols" are
recognized as notation guides and exempt from definition requirements.

Scope:
- Whole tree by default (`INFORMAL_DEFS_DIFF_SCOPED` unset or false).
- Diff-scoped on request (`INFORMAL_DEFS_DIFF_SCOPED=true`), evaluating only
  lines added since `INFORMAL_DEFS_BASE_REF` or in a diff file (`--diff`).
"""

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd"
DEFAULT_PATHS_IGNORE = ".git, .github, tests, test, vendor, scratch, _site, node_modules, .venv, venv"

# Common labels that use bold prefixes but are not concept definitions
COMMON_LABELS = frozenset({
    "note", "warning", "caution", "tip", "important", "example", "remark",
    "definition", "step", "case", "proof", "solution", "answer", "question",
    "summary", "recap", "prerequisite", "prerequisites", "todo", "fixme",
})

HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+)$")

EXEMPT_HEADING_TITLE_RE = re.compile(
    r"^(?:notation|typographic\s+conventions?|conventions?|symbols?|glossary\s+of\s+notation)\b",
    re.IGNORECASE,
)

DEFINITIONS_HEADING_TITLE_RE = re.compile(
    r"^(?:definitions?|key\s+definitions?)\b",
    re.IGNORECASE,
)

FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})")
# Pandoc also accepts a bare class word after the fence ("::: proof").
DIV_FENCE_START = re.compile(
    r"^(?P<fence>:{3,})\s*(?:\{(?P<attrs>[^}]+)\}|(?P<bare>[A-Za-z][\w-]*))?\s*:*\s*$"
)
DIV_FENCE_END = re.compile(r"^(?P<fence>:{3,})\s*$")

# Definition or theorem crossref prefixes: def, thm, lem, cor, prp, cnj, exr, exm, rem, sol, clm
THEOREM_DIV_RE = re.compile(
    r"(?:^|\s)(?:#(?:def|thm|lem|cor|prp|cnj|exr|exm|rem|sol|clm|prf)-|\.(?:definition|theorem|lemma|corollary|proposition|proof|sol|solution))\b"
)

# Directives
FILE_OPT_OUT_RE = re.compile(
    r"<!--\s*(?:check-informal-definitions|detect-informal-definitions):\s*ignore-file\s*-->",
    re.IGNORECASE,
)
LINE_OPT_OUT_RE = re.compile(
    r"<!--\s*(?:check-informal-definitions|detect-informal-definitions):\s*(?:allow|ignore|opt-out|disable)\s*-->",
    re.IGNORECASE,
)

# Inline code span regex (`...`) to strip before running prose detection patterns
INLINE_CODE_SPAN_RE = re.compile(r"`[^`\n]*`")

# Detection Patterns: optionally allow inline math or symbol parenthetical between term and verb
# (e.g. `A **random variable** $X$ is a...` or `The **estimator** $\hat{\theta}$ is defined as...`)
BOLD_DEF_RE = re.compile(
    r"(?i)(?:\b(?:A|An|The)\s+)?\*\*(?P<term>[A-Za-z][a-zA-Z0-9 _-]{1,60}(?<![.,;:?!]))\*\*(?:\s+\$[^\$\n]+\$|\s+\([^)\n]+\))?(?::\s*|\s+)(?P<defining>is\s+(?!this\b|it\b|there\b|that\b|he\b|she\b|they\b)[a-zA-Z]+|are\s+(?!these\b|they\b|there\b|those\b)[a-zA-Z]+|means\b|refers\s+to\b|\\eqdef\b|\\triangleq\b)"
)

BOLD_COLON_DEF_RE = re.compile(
    r"(?i)\*\*(?P<term>[A-Za-z][a-zA-Z0-9 _-]{1,60}(?<![.,;:?!]))\*\*(?:\s+\$[^\$\n]+\$|\s+\([^)\n]+\))?:\s+(?P<defining>(?:a|an|the)\s+[a-zA-Z]|is\s+(?:defined\s+as|the|a|an)\b|refers\s+to\b|means\b)"
)

EQDEF_RE = re.compile(r"\\(?:eqdef|triangleq)\b")
# A local abbreviation ("Let $S_n \eqdef ...$", "write $m \eqdef ...$") names a
# quantity for one argument; it defines no term.
LOCAL_ABBREV_RE = re.compile(
    r"(?i)\b(?:let|write|set|put|denote|abbreviate)\s+\$[^$]*\\(?:eqdef|triangleq)\b"
)
IS_BEFORE_MATH_RE = re.compile(r"(?i)\b(?:is|are):\s*$")
# "X is:" before display math names a term only when the sentence says so: a
# bold term, or a naming verb. "The inner derivative is:" computes a value.
NAMING_CUE_RE = re.compile(
    r"(?i)\*\*[^*]+\*\*|\b(?:called|defined|known\s+as|termed|we\s+define)\b"
)
# A bold label that opens a line or list item ("- **Improvement**: ...") is a
# label, not a term being defined.
LEADING_LABEL_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])?\s*\*\*[^*\n]+\*\*\s*[:.]")
# Notation, not a definition: "**Expectation** is denoted $\E{}$".
NOTATION_VERB_RE = re.compile(r"(?i)^(?:is|are)\s+(?:denoted|written|set\s+to)\b")


@dataclass(frozen=True)
class Finding:
    file: Path
    line: int
    rule: str
    term: str
    message: str
    snippet: str


def is_label_or_meta(term: str) -> bool:
    t = term.strip().lower()
    if t in COMMON_LABELS:
        return True
    if any(t.startswith(prefix) for prefix in ("fig", "tab", "step ", "case ")):
        return True
    if t.startswith("-"):
        return True
    return False


def scan_file_lines(
    path: Path, lines: Sequence[str], added_lines: Optional[Set[int]] = None
) -> List[Finding]:
    """Scan the lines of a file for informal definitions."""
    findings: List[Finding] = []

    # Check file-level opt-out
    full_text = "\n".join(lines)
    if FILE_OPT_OUT_RE.search(full_text):
        return findings

    in_yaml = False
    in_code_fence = False
    code_fence_char = ""
    code_fence_len = 0
    in_html_comment = False

    div_stack: List[Tuple[str, bool]] = []  # (fence, is_def_or_theorem)
    exempt_section_level: Optional[int] = None
    definitions_section_level: Optional[int] = None

    for idx, line in enumerate(lines, start=1):
        # 1. Frontmatter
        if idx == 1 and line.strip() == "---":
            in_yaml = True
            continue
        if in_yaml:
            if line.strip() in ("---", "..."):
                in_yaml = False
            continue

        # 2. HTML comments
        if "<!--" in line and "-->" not in line:
            in_html_comment = True
            continue
        if in_html_comment:
            if "-->" in line:
                in_html_comment = False
            continue

        # 3. Code fences
        m_fence = FENCE_RE.match(line)
        if m_fence:
            marker = m_fence.group(2)
            char = marker[0]
            length = len(marker)
            if not in_code_fence:
                in_code_fence = True
                code_fence_char = char
                code_fence_len = length
                continue
            elif char == code_fence_char and length >= code_fence_len:
                in_code_fence = False
                continue

        if in_code_fence:
            continue

        # 4. Heading changes
        m_heading = HEADING_RE.match(line)
        if m_heading:
            level = len(m_heading.group("hashes"))
            title = m_heading.group("title").strip()

            if exempt_section_level is not None and level <= exempt_section_level:
                exempt_section_level = None
            if definitions_section_level is not None and level <= definitions_section_level:
                definitions_section_level = None

            if EXEMPT_HEADING_TITLE_RE.match(title):
                exempt_section_level = level
            elif DEFINITIONS_HEADING_TITLE_RE.match(title):
                definitions_section_level = level

        in_exempt_section = exempt_section_level is not None
        in_definitions_section = definitions_section_level is not None

        # 5. Div tracking (::: {#def-...} or :::: {#def-...})
        stripped = line.strip()
        m_div_open = DIV_FENCE_START.match(stripped)
        if m_div_open and (m_div_open.group("attrs") or m_div_open.group("bare")):
            fence = m_div_open.group("fence")
            attrs = m_div_open.group("attrs") or "." + m_div_open.group("bare")
            is_def = bool(THEOREM_DIV_RE.search(attrs))
            div_stack.append((fence, is_def))
            continue

        m_div_plain = DIV_FENCE_END.match(stripped)
        if m_div_plain:
            fence = m_div_plain.group("fence")
            fence_len = len(fence)
            if div_stack and len(div_stack[-1][0]) <= fence_len:
                div_stack.pop()
                continue
            elif div_stack and any(len(f) == fence_len for f, _ in div_stack):
                while div_stack and len(div_stack[-1][0]) != fence_len:
                    div_stack.pop()
                if div_stack:
                    div_stack.pop()
                continue
            else:
                div_stack.append((fence, False))
                continue

        # Check line-level opt-out
        if LINE_OPT_OUT_RE.search(line):
            continue

        # If inside a formal definition or theorem div, skip
        if any(is_def for _, is_def in div_stack):
            continue

        # If in an exempt section (Notation / Conventions), skip
        if in_exempt_section:
            continue

        # Table rows or markdown formatting rules
        if stripped.startswith("|") and stripped.endswith("|"):
            continue

        # Check if line should be examined under diff scoping
        is_targeted_line = added_lines is None or idx in added_lines

        # Strip inline code spans (`...`) so backticked symbols and references do not trigger findings
        prose_line = INLINE_CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), line)

        # Pattern 1: Bold term followed by defining language
        m_bold = BOLD_DEF_RE.search(prose_line)
        if m_bold and NOTATION_VERB_RE.match(m_bold.group("defining")):
            m_bold = None
        if m_bold:
            term = m_bold.group("term")
            if not is_label_or_meta(term):
                if is_targeted_line:
                    findings.append(
                        Finding(
                            file=path,
                            line=idx,
                            rule="bold-prose-definition",
                            term=term,
                            message=f"Concept '**{term}**' is defined in prose rather than in a formal ::: {{#def-...}} div.",
                            snippet=line.strip(),
                        )
                    )
                continue

        m_colon = BOLD_COLON_DEF_RE.search(prose_line)
        if m_colon and LEADING_LABEL_RE.match(prose_line):
            m_colon = None
        if m_colon:
            term = m_colon.group("term")
            if not is_label_or_meta(term):
                if is_targeted_line:
                    findings.append(
                        Finding(
                            file=path,
                            line=idx,
                            rule="bold-colon-definition",
                            term=term,
                            message=f"Concept '**{term}**' is defined in prose with colon definition rather than in a formal ::: {{#def-...}} div.",
                            snippet=line.strip(),
                        )
                    )
                continue

        # Pattern 2: \eqdef or \triangleq outside a def div
        if EQDEF_RE.search(prose_line):
            if is_targeted_line and not LOCAL_ABBREV_RE.search(prose_line):
                findings.append(
                    Finding(
                        file=path,
                        line=idx,
                        rule="eqdef-outside-div",
                        term="\\eqdef",
                        message="Mathematical definition operator (\\eqdef or \\triangleq) used outside a formal ::: {#def-...} div.",
                        snippet=line.strip(),
                    )
                )
            continue

        # Pattern 3: Heading titled Definitions over prose without def div
        if in_definitions_section and stripped and not stripped.startswith("#"):
            if is_targeted_line:
                m_any_bold = re.search(r"\*\*(?P<term>[A-Za-z][a-zA-Z0-9 _-]{1,60}(?<![.,;:?!]))\*\*", prose_line)
                if m_any_bold and not is_label_or_meta(m_any_bold.group("term")):
                    findings.append(
                        Finding(
                            file=path,
                            line=idx,
                            rule="definitions-section-prose",
                            term=m_any_bold.group("term"),
                            message=f"Concept '**{m_any_bold.group('term')}**' defined under '### Definitions' heading in prose instead of in a formal ::: {{#def-...}} div.",
                            snippet=line.strip(),
                        )
                    )
                    continue

        # Pattern 4: Naming sentence ending with is: or are: before display math
        # A leading bold label ("**Note**: ...") is not a bold term.
        cue_text = LEADING_LABEL_RE.sub("", prose_line, count=1)
        if IS_BEFORE_MATH_RE.search(prose_line) and NAMING_CUE_RE.search(cue_text):
            # Look ahead for next non-blank line
            next_idx = idx
            while next_idx < len(lines):
                next_line = lines[next_idx].strip()
                if not next_line:
                    next_idx += 1
                    continue
                if next_line.startswith("$$"):
                    if is_targeted_line:
                        findings.append(
                            Finding(
                                file=path,
                                line=idx,
                                rule="naming-sentence-display-math",
                                term="is:",
                                message="Naming sentence ending in 'is:'/'are:' immediately before display math outside a formal ::: {#def-...} div.",
                                snippet=line.strip(),
                            )
                        )
                break

    return findings


# A def div defines one term (ai-config shared/writing/lecture-conventions.md,
# informal-definitions.md Shape 4). An alias of that term is bold too, but is
# introduced by a cue such as "also called", which the check recognizes.
BOLD_SPAN_RE = re.compile(r"\*\*(?P<term>[^*\n]+?)\*\*")
ALIAS_CUE_RE = re.compile(
    r"(?i)\b(?:also\s+(?:called|known\s+as|written|termed)"
    r"|sometimes\s+(?:called|known\s+as)"
    r"|known\s+as|called|or|aka|a\.k\.a\.|termed"
    r"|other\s+(?:names?|terms?)|synonyms?)\s*:?\s*(?:(?:the|a|an)\s*)?$"
)
DEF_ID_RE = re.compile(r"#def-")
# The text between two bold aliases of one list: "A, B", "A and B", "A, or B".
LIST_JOIN_RE = re.compile(r"\s*(?:,\s*)?(?:(?:and|or)\s+)?")
TITLE_RE = re.compile(r"^#{1,6}\s+(?P<title>.+)$")
INLINE_MATH_RE = re.compile(r"(?<![\\$])\$(?!\s|\$)[^$\n]*?(?<![\s\\])\$(?!\d)")
ABBREV_TERM_RE = re.compile(r"^[A-Z][A-Z0-9]{0,5}s?$")
# A hyperlink or a Quarto cross-reference (@def-x) in a def div.
LINK_RE = re.compile(
    r"\]\([^)\s]+\)|(?<![\w@])@(?:def|thm|lem|cor|prp|cnj|exm|rem|sec|eq)-[\w-]+"
)
DIV_OPEN_RE = re.compile(r"^(?P<fence>:{3,})\s*(?P<attrs>[^:\s].*)$")
DIV_CLOSE_RE = re.compile(r"^(?P<fence>:{3,})\s*$")


# Stems of the words in the title of every def div in the scanned files; set by
# main(). A def div with prose and no link is reported only when its prose uses
# one of these words (other than its own title): a foundational definition has
# no other defined term to link. None (the default) reports every such div.
DEFINED_STEMS: Optional[Set[str]] = None
STEM_LEN = 5


def word_stems(text: str) -> Set[str]:
    """Stems of the words of five or more letters in ``text``."""
    words = re.findall(r"[a-z]+", re.sub(r"\]\([^)]*\)", " ", text).lower())
    return {w[:STEM_LEN] for w in words if len(w) >= STEM_LEN}


def defined_title_stems(texts: List[List[str]]) -> Set[str]:
    """Stems of the title words of the def divs in ``texts`` (lists of lines)."""
    stems: Set[str] = set()
    for lines in texts:
        for idx, raw in enumerate(lines):
            m_open = DIV_OPEN_RE.match(raw.strip())
            if not (m_open and DEF_ID_RE.search(m_open.group("attrs"))):
                continue
            attr_title = re.search(r'title="([^"]*)"', m_open.group("attrs"))
            if attr_title:
                stems |= word_stems(attr_title.group(1))
                continue
            for follow in lines[idx + 1 : idx + 4]:
                tm = TITLE_RE.match(follow.strip())
                if tm:
                    stems |= word_stems(tm.group("title"))
                    break
    return stems


def _blank(match: "re.Match[str]") -> str:
    return " " * len(match.group(0))


def _strip_comments(line: str, in_comment: bool) -> Tuple[str, bool]:
    """Blank the HTML-comment parts of a line; return it and the carried state."""
    out: List[str] = []
    pos = 0
    while pos < len(line):
        if in_comment:
            end = line.find("-->", pos)
            if end == -1:
                out.append(" " * (len(line) - pos))
                return "".join(out), True
            out.append(" " * (end + 3 - pos))
            pos, in_comment = end + 3, False
        else:
            start = line.find("<!--", pos)
            if start == -1:
                out.append(line[pos:])
                break
            out.append(line[pos:start])
            pos, in_comment = start, True
    return "".join(out), in_comment


def _term_key(term: str) -> str:
    """Normalize a term so that case, spacing and a plural 's' do not matter."""
    key = re.sub(r"\s+", " ", term.lower()).strip()
    return key[:-1] if len(key) > 3 and key.endswith("s") else key


def _is_countable_term(term: str, before: str) -> bool:
    """Whether a bold span in a def div names a defined term.

    Skips labels, spans with fewer than two letters (symbols such as **x**),
    bare abbreviations (**PPV**), and spans written inside parentheses or
    quotation marks, which gloss the term instead of defining a second one.
    """
    if term.endswith(":") or is_label_or_meta(term):
        return False
    if len(re.findall(r"[A-Za-z]", term)) < 2 or "$" in term:
        return False
    if ABBREV_TERM_RE.match(term):
        return False
    if before.count("(") > before.count(")") or before.rstrip().endswith(
        ('"', "'", "“", "‘")
    ):
        return False
    return True


def _term_stems(term: str) -> Set[str]:
    """Five-letter stems of a term's words, ignoring a parenthesized gloss."""
    words = re.findall(r"[a-z]+", re.sub(r"\([^)]*\)", " ", term.lower()))
    return {w[:STEM_LEN] for w in words}


def _is_variant(term: str, terms: List[str]) -> bool:
    """Whether every word of ``term`` repeats a counted term's words.

    "convergent" after "converges", "residuals" after "residual vector" and
    "mean squared error" after "population mean squared error" are variants of
    a term already counted, not second terms.
    """
    stems = _term_stems(term)
    return bool(stems) and any(stems <= _term_stems(t) for t in terms)


def _is_alias(context: str, terms: List[str]) -> bool:
    """Whether a bold span follows an alias cue ("also called", "or")."""
    return bool(terms) and bool(ALIAS_CUE_RE.search(context.rstrip().rstrip(",")))


def scan_def_div_terms(
    path: Path, lines: Sequence[str], added_lines: Optional[Set[int]] = None
) -> List[Finding]:
    """Flag a `::: {#def-...}` div that defines more than one term.

    A def div defines one term; aliases of it are bold too but follow a cue such
    as "also called". Counts distinct bold terms in the div's own prose: a term
    repeated (or in the plural), an abbreviation, a gloss in parentheses or
    quotes, a symbol, bold inside math, and bold inside a nested div (a callout)
    are not counted. A cue may wrap onto the previous line.
    In diff-scoped mode the div is examined when any line of it was added.
    """
    findings: List[Finding] = []
    if FILE_OPT_OUT_RE.search("\n".join(lines)):
        return findings

    stack: List[int] = []  # fence lengths of the open divs, outermost first
    def_depth = 0  # len(stack) once the outermost def div is open; 0 when none
    open_line = 0
    end_line = 0
    terms: List[str] = []
    seen: Set[str] = set()
    prev_prose = ""
    code_fence = ""
    in_comment = False
    in_yaml = False
    opted_out = False
    has_link = False
    has_prose = False
    div_words: Set[str] = set()  # word stems in the div's prose
    own_words: Set[str] = set()  # word stems of the div's own title

    def flush() -> None:
        touched = added_lines is None or any(
            open_line <= n <= end_line for n in added_lines
        )
        if opted_out or not touched:
            return
        needs_link = DEFINED_STEMS is None or bool(
            div_words - own_words and (div_words - own_words) & DEFINED_STEMS
        )
        if has_prose and not has_link and needs_link:
            findings.append(
                Finding(
                    file=path,
                    line=open_line,
                    rule="no-link-in-definition",
                    term="",
                    message=(
                        "Definition div links no other term: hyperlink each "
                        "technical term on first use in the div, and give any "
                        "term with no definition its own def div."
                    ),
                    snippet="",
                )
            )
        if len(terms) < 2:
            return
        listed = ", ".join(terms)
        findings.append(
            Finding(
                file=path,
                line=open_line,
                rule="multiple-terms-in-definition",
                term=listed,
                message=(
                    f"Definition div defines more than one term ({listed}); "
                    "one term per def div, with aliases introduced by 'also called'."
                ),
                snippet=listed,
            )
        )

    for idx, raw in enumerate(lines, start=1):
        if idx == 1 and raw.strip() == "---":
            in_yaml = True
            continue
        if in_yaml:
            in_yaml = raw.strip() not in ("---", "...")
            continue
        m_code = FENCE_RE.match(raw)
        if code_fence:
            if (
                m_code
                and m_code.group(2)[0] == code_fence[0]
                and len(m_code.group(2)) >= len(code_fence)
                and not raw.strip()[len(m_code.group(2)) :].strip()
            ):
                code_fence = ""
            continue
        if m_code and not in_comment:
            code_fence = m_code.group(2)
            continue
        line, in_comment = _strip_comments(raw, in_comment)
        stripped = line.strip()
        m_open = DIV_OPEN_RE.match(stripped)
        m_close = DIV_CLOSE_RE.match(stripped)
        if m_open:
            stack.append(len(m_open.group("fence")))
            if not def_depth and DEF_ID_RE.search(m_open.group("attrs")):
                def_depth = len(stack)
                open_line, end_line = idx, idx
                terms, seen, prev_prose, opted_out = [], set(), "", False
                has_link, has_prose = False, False
                div_words, own_words = set(), set()
            continue
        if m_close and stack:
            if len(m_close.group("fence")) >= stack[-1]:
                stack.pop()
                if def_depth and len(stack) < def_depth:
                    end_line = idx
                    flush()
                    def_depth = 0
            continue
        if not def_depth or len(stack) > def_depth:
            continue
        end_line = idx
        if LINE_OPT_OUT_RE.search(raw):
            opted_out = True
        if TITLE_RE.match(stripped) and not terms:
            own_words |= word_stems(stripped)
            continue
        prose = INLINE_CODE_SPAN_RE.sub(_blank, line)
        div_words |= word_stems(BOLD_SPAN_RE.sub(" ", INLINE_MATH_RE.sub(" ", prose)))
        for bold in BOLD_SPAN_RE.finditer(prose):
            own_words |= word_stems(bold.group("term"))
        alias_end = -1
        if LINK_RE.search(prose):
            has_link = True
        prose = INLINE_MATH_RE.sub(_blank, prose)
        if prose.strip() and not TITLE_RE.match(stripped):
            has_prose = True
        for m in BOLD_SPAN_RE.finditer(prose):
            term = m.group("term").strip()
            before = prose[: m.start()]
            after = prose[m.end() :].lstrip()
            # A paragraph or list label ("**Discrete case.**", "1. **Positivity**:")
            # and a table cell name no term.
            if (
                term.endswith(".")
                or stripped.startswith("|")
                or (LEADING_LABEL_RE.match(prose) and m.start() == prose.find("**"))
                or (after.startswith(":") and not before.strip())
            ):
                continue
            if _is_variant(term, terms):
                seen.add(_term_key(term))
                continue
            if re.fullmatch(r"\s*(?:(?:the|a|an)\s*)?", before, re.I):
                context = prev_prose.rstrip() + " " + before
            else:
                context = before
            key = _term_key(term)
            countable = _is_countable_term(term, before)
            joins_alias = alias_end >= 0 and LIST_JOIN_RE.fullmatch(
                before[alias_end:]
            )
            if key in seen or not countable or joins_alias or _is_alias(context, terms):
                if countable and (joins_alias or _is_alias(context, terms)):
                    alias_end = m.end()
                seen.add(key)
                continue
            seen.add(key)
            terms.append(term)
        if prose.strip():
            prev_prose = prose
    return findings


def _added_line_numbers(diff: str, repo_root: Path) -> Dict[Path, Set[int]]:
    """{repo_root / path: added line numbers} from a ``-U0`` diff."""
    added, _deleted = diffscope.parse_diff(diff)
    return {repo_root / rel: set(lines) for rel, lines in added.items()}


def get_diff_added_lines(
    base_ref: str, repo_root: Path, pathspecs: Sequence[str]
) -> Optional[Dict[Path, Set[int]]]:
    """Compute mapping of Path -> set of added line numbers since base_ref."""
    mb = diffscope.run_git(["merge-base", base_ref, "HEAD"])
    if mb is None or not mb.strip():
        return None
    diff = diffscope.run_git(["diff", "-U0", mb.strip(), "--", *pathspecs])
    if diff is None:
        return None
    return _added_line_numbers(diff, repo_root)


def parse_diff_file(diff_path: Path, repo_root: Path) -> Dict[Path, Set[int]]:
    """Parse added line numbers from a saved diff file."""
    if not diff_path.is_file():
        return {}
    try:
        content = diff_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    return _added_line_numbers(content, repo_root)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check for technical definitions written in prose rather than Quarto def divs."
    )
    parser.add_argument(
        "--path",
        default=os.getenv("INFORMAL_DEFS_PATH", "."),
        help="Target directory or file path to check.",
    )
    parser.add_argument(
        "--globs",
        default=os.getenv("INFORMAL_DEFS_GLOBS", DEFAULT_GLOBS),
        help="Space-separated file globs to check (default: '*.qmd').",
    )
    parser.add_argument(
        "--paths-ignore",
        default=os.getenv("INFORMAL_DEFS_PATHS_IGNORE", DEFAULT_PATHS_IGNORE),
        help="Comma-separated paths or glob patterns to ignore.",
    )
    parser.add_argument(
        "--fail",
        default=os.getenv("INFORMAL_DEFS_FAIL", "false"),
        help="Whether to exit with non-zero status on findings (default: 'false').",
    )
    parser.add_argument(
        "--diff-scoped",
        default=os.getenv("INFORMAL_DEFS_DIFF_SCOPED", "false"),
        help="Report only lines added in git diff (default: 'false').",
    )
    parser.add_argument(
        "--base-ref",
        default=os.getenv("INFORMAL_DEFS_BASE_REF", ""),
        help="Git base ref for diff-scoped checking.",
    )
    parser.add_argument(
        "--diff",
        default=os.getenv("INFORMAL_DEFS_DIFF_FILE", ""),
        help="Path to unified diff file to scan added lines from.",
    )
    parser.add_argument(
        "--output-markdown",
        default=os.getenv("INFORMAL_DEFS_OUTPUT_MARKDOWN", ""),
        help="Path to write Markdown summary report.",
    )
    parser.add_argument(
        "--output-json",
        default=os.getenv("INFORMAL_DEFS_OUTPUT_JSON", ""),
        help="Path to write JSON findings report.",
    )

    args = parser.parse_args()

    repo_root = Path.cwd()
    target_path = Path(args.path).resolve()
    globs = [g.strip() for g in args.globs.split() if g.strip()]
    ignore_patterns = diffscope.split_list(args.paths_ignore)
    should_fail = str(args.fail).lower() in ("true", "1", "yes")
    diff_scoped = str(args.diff_scoped).lower() in ("true", "1", "yes")
    base_ref = args.base_ref.strip()
    diff_file = Path(args.diff).resolve() if args.diff.strip() else None

    # Discover target files
    files_to_scan: List[Path] = []
    if target_path.is_file():
        files_to_scan.append(target_path)
    elif target_path.is_dir():
        # List tracked files via git ls-files if git repo, else rglob
        git_success = False
        try:
            cmd = ["git", "ls-files", "-z", "--"] + globs
            res = subprocess.run(
                cmd, cwd=target_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if res.returncode == 0:
                git_success = True
                for raw_p in res.stdout.split(b"\0"):
                    if raw_p:
                        line = raw_p.decode("utf-8", errors="replace").strip()
                        if line:
                            p = (target_path / line).resolve()
                            if p.is_file():
                                files_to_scan.append(p)
        except Exception:
            pass

        if not git_success:
            for g in globs:
                for p in target_path.rglob(g):
                    if p.is_file():
                        files_to_scan.append(p.resolve())

    # Filter out ignored paths using anchored regexes matching sibling checkers
    ignores_compiled = diffscope.compile_ignores(ignore_patterns)
    filtered_files: List[Path] = []
    for f in sorted(set(files_to_scan)):
        try:
            rel = f.relative_to(repo_root)
        except ValueError:
            rel = f
        rel_str = str(rel).replace("\\", "/")
        if diffscope.ignored(rel_str, ignores_compiled) or diffscope.ignored(f.name, ignores_compiled):
            continue
        filtered_files.append(f)

    global DEFINED_STEMS
    corpus: List[List[str]] = []
    for f in filtered_files:
        try:
            corpus.append(f.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
    DEFINED_STEMS = defined_title_stems(corpus)

    # Compute diff-added lines if requested
    added_lines_map: Optional[Dict[Path, Set[int]]] = None
    if diff_file and diff_file.is_file():
        added_lines_map = parse_diff_file(diff_file, repo_root)
    elif diff_scoped:
        if base_ref:
            added_lines_map = get_diff_added_lines(base_ref, repo_root, globs)
            if added_lines_map is None:
                print(
                    f"::warning::check-informal-definitions: Could not compute diff against base-ref '{base_ref}'. Skipping diff-scoped check.",
                    file=sys.stderr,
                )
                return 0
        else:
            print(
                "::warning::check-informal-definitions: diff-scoped requested but no base-ref or diff-file provided. Skipping.",
                file=sys.stderr,
            )
            return 0

    all_findings: List[Finding] = []
    for f in filtered_files:
        added_lines = added_lines_map.get(f) if added_lines_map is not None else None
        if added_lines_map is not None and not added_lines:
            # File had no added lines in diff
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"Warning: could not read {f}: {e}", file=sys.stderr)
            continue
        lines = content.splitlines()
        findings = scan_file_lines(f, lines, added_lines)
        findings.extend(scan_def_div_terms(f, lines, added_lines))
        all_findings.extend(findings)

    # Report results
    if all_findings:
        print(f"check-informal-definitions: Found {len(all_findings)} definition problem(s) (informal definitions in prose or bundled def divs):\n")
        for f in all_findings:
            try:
                rel = f.file.relative_to(repo_root)
            except ValueError:
                rel = f.file
            rel_str = str(rel).replace("\\", "/")
            print(f"  {rel_str}:{f.line}: [{f.rule}] {f.message}")
            print(f"    Snippet: {f.snippet}\n")
            # GitHub annotation
            severity = "error" if should_fail else "warning"
            print(
                f"::{severity} file={rel_str},line={f.line},title=Definition problem::[{f.rule}] {f.message}"
            )

    else:
        print("check-informal-definitions: Clean. No informal definitions found.")

    if args.output_markdown:
        out_md = Path(args.output_markdown)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        with open(out_md, "w", encoding="utf-8") as mdf:
            mdf.write("### Definition Problems\n\n")
            if all_findings:
                mdf.write(
                    "Some technical concepts appear to be defined in running prose "
                    "rather than inside formal Quarto definition divs (`::: {#def-...}`), "
                    "or a definition div defines more than one term. "
                    "Every technical concept defined in content repositories must have its own formal "
                    "`::: {#def-...}` div with a worked example, and each div defines one term.\n\n"
                )
                for f in all_findings:
                    try:
                        rel = f.file.relative_to(repo_root)
                    except ValueError:
                        rel = f.file
                    rel_str = str(rel).replace("\\", "/")
                    mdf.write(f"- `{rel_str}:{f.line}`: **{f.term}** ({f.rule})\n  > {f.snippet}\n")
            else:
                mdf.write("Clean. No informal definitions found.\n")

    if args.output_json:
        import json

        out_json = Path(args.output_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        report_data = {
            "total_findings": len(all_findings),
            "findings": [
                {
                    "file": str(
                        f.file.relative_to(repo_root) if repo_root in f.file.parents else f.file
                    ).replace("\\", "/"),
                    "line": f.line,
                    "rule": f.rule,
                    "term": f.term,
                    "message": f.message,
                    "snippet": f.snippet,
                }
                for f in all_findings
            ],
        }
        with open(out_json, "w", encoding="utf-8") as jf:
            json.dump(report_data, jf, indent=2)

    if all_findings and should_fail:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
