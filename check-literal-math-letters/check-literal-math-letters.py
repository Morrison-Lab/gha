#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag literal Latin and Greek letters in math, where a semantic macro belongs.

The lab's rule (Morrison-Lab/gha#1077, check 1): every math symbol is a
semantic macro from ``Morrison-Lab/macros`` (``\outvar``, ``\predvar``,
``\param``, ...). No literal letter appears in math outside a passage about the
notation itself, except a one-off with no semantic category.

What is flagged, inside inline ``$...$`` and display ``$$...$$`` (and
``\begin{equation|align|...}``) math of ``.qmd``/``.md``/``.Rmd`` files:

- a standalone single Latin letter, that is, a maximal run of exactly one ASCII
  letter that is not part of a ``\command`` name, such as the ``y`` in
  ``$y_i$``;
- any Greek command (``\alpha`` ... ``\omega``, ``\varepsilon``, ``\varphi``,
  capitals such as ``\Gamma``) and any literal Greek character.

What is not flagged:

- the argument of a text-like command: ``\text``, ``\textrm``, ``\mathrm``,
  ``\operatorname``, ``\mbox`` and their relatives; ``\mathbb`` (set and
  operator names, which ``check-raw-math`` covers); and reference-like
  commands (``\label``, ``\tag``, ``\eqref``, ``\begin``, ``\end``, ...);
- runs of two or more letters (``\sin`` written without a backslash is a
  different mistake, and ``x y`` written as ``xy`` is not a *single* letter);
- code fences, code spans, HTML comments and YAML front matter;
- any ``::: {.notation}`` div (a passage that discusses the notation itself,
  where a literal letter is the point);
- a blockquote paragraph that opens with a cross mark (a counter-example of
  what not to write), up to the next empty ``>`` line, a line that opens with
  a check mark, or a non-quote line;
- macro definitions (a math span that opens with ``\newcommand``, ``\def`` and
  the like), which are check 2's concern;
- a line carrying, or following, ``<!-- check-literal-math-letters: allow -->``,
  and a file carrying ``<!-- check-literal-math-letters: ignore-file -->``.

Strict by design: there is no allow-list for indices or dummy variables. The
rule says to find the category first, and the false-positive rate is measured
rather than assumed (see the reference page).

Design notes, in the model of ``check-new-line-breaks``:

- **Diff-scoped by default.** Only lines *added* since ``LML_BASE_REF`` are
  reported, so a corpus that already carries literal letters is not reflagged
  on every unrelated edit. The whole file is parsed (a display block opens on
  one line and its letters sit on the next), and only findings on added lines
  are kept. An added line whose exact text was also deleted in the same diff is
  treated as moved, not new.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed (a shallow clone), the check skips with a warning. It never falls
  back to a whole-tree scan, which would reflag all pre-existing letters.
  ``LML_WHOLE_TREE=true`` asks for the whole tree explicitly.
- **Working-tree-aware.** The diff is taken from the merge base to the working
  tree, so a staged or unstaged edit is examined too. In CI the tree is clean
  and this is the same as committed content. A brand new untracked file is
  invisible to ``git diff``; stage it to have it examined.
- **Warn-only by default** (``LML_FAIL`` defaults to false).
- **The search space is reported.** Every run prints how many files, added
  lines and math spans it examined, so zero examined reads differently from
  examined and clean.

Configuration (environment variables, set by the composite action):
  LML_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  LML_GLOBS         Space-separated git pathspecs (default: '*.qmd *.md *.Rmd').
  LML_PATHS_IGNORE  Comma/newline-separated glob patterns (relative paths) to
                    skip. Supports ``*``, ``?`` and recursive ``**``.
  LML_FAIL          "true" => exit 1 on a finding; default "false" => annotate
                    with warnings only.
  LML_WHOLE_TREE    "true" => scan every tracked matching file in full.
"""

import os
import re
import subprocess
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd *.md *.Rmd"
_DEFAULT_FAIL = False

# -- Rule tables -------------------------------------------------------------

_GREEK_LOWER = (
    "alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota "
    "kappa varkappa lambda mu nu xi pi varpi rho varrho sigma varsigma tau "
    "upsilon phi varphi chi psi omega"
).split()
_GREEK_UPPER = (
    "Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega"
).split()
GREEK_COMMANDS = frozenset(_GREEK_LOWER + _GREEK_UPPER)

# Commands whose braced argument is not math symbols: text, names, labels.
# The argument is skipped whole, so a letter inside it is never flagged.
SKIP_ARG_COMMANDS = frozenset({
    "text", "textrm", "textbf", "textit", "textsf", "texttt", "textnormal",
    "textup", "textsc", "mbox", "hbox", "operatorname", "mathrm", "mathsf",
    "mathtt", "mathbb", "mathbbm", "label", "tag", "eqref", "ref", "autoref",
    "cref", "Cref", "begin", "end", "color", "textcolor", "href", "url",
    "cite", "hspace", "vspace", "phantom", "hphantom", "vphantom",
    "cssId", "class", "htmlClass", "bbox", "DeclareMathOperator",
})

# After these, a second braced argument is also not math (the column spec).
SECOND_ARG_ENVIRONMENTS = frozenset({"array", "alignat", "alignedat", "tabular"})

# Commands that open a macro definition: such a span is check 2's concern.
DEFINITION_COMMANDS = ("\\newcommand", "\\renewcommand", "\\providecommand",
                       "\\def", "\\DeclareMathOperator", "\\gdef",
                       "\\let", "\\newenvironment")

# Top-level display environments that open math at the start of a line.
DISPLAY_ENVIRONMENTS = ("equation", "align", "alignat", "gather", "multline",
                        "flalign", "eqnarray")

# Suggested macros, each verified against Morrison-Lab/macros `macros.qmd`
# and `interpretations.tsv` (2026-10-16): \outvar prints y, \Outvar prints Y,
# \predvar prints x, \Predvar prints X, \nobs is `n`, \loss is `L`,
# \param is `\theta`, \regcoef is `\beta`, \eps is `\varepsilon`,
# \mean is `\mu`.
LATIN_SUGGESTIONS = {
    "y": r"\outvar if this is the outcome variable",
    "Y": r"\Outvar if this is the random outcome variable",
    "x": r"\predvar if this is the predictor variable",
    "X": r"\Predvar if this is the random predictor variable",
    "n": r"\nobs if this is the number of observations",
    "L": r"\loss if this is the loss function",
    "e": r"\euler (or \e{...} for a power) if this is Euler's number",
}
GREEK_SUGGESTIONS = {
    "theta": r"\param if this is a generic parameter",
    "beta": r"\regcoef if this is a regression coefficient",
    "varepsilon": r"\eps if this is the error term",
    "mu": r"\mean if this is the population mean",
}
# A line that names the log-odds (or logit) and writes it as a bare `z` or
# `F` in math. The course symbol is \logodds (eta); the notes once used `F`
# and `z` for it. `z` and `F` have no suggestion above, so this rule runs in
# both modes (Ezra, 2026-10-26, lds#1411). It is deliberately narrow:
# a letter that is a subscript, superscript, applied function (`F(x)`, `F^{-1}`),
# part of a longer symbol (`x_z`, `z_i`), or inside a `\text{}`/`\mathrm{}`
# argument is skipped, and so is a line that names a Wald statistic, a
# quantile or a test, where `z` and `F` are the standard symbols.
# `\logodds` itself is not context: the boundary and lookbehind exclude it.
LOGODDS_CONTEXT_RE = re.compile(r"(?<!\\)\b(?:log[- ]?odds|logits?)\b", re.IGNORECASE)
LOGODDS_EXEMPT_RE = re.compile(r"\b(?:wald|quantiles?|statistics?|tests?|z-scores?)\b", re.IGNORECASE)
LOGODDS_LETTER_RE = re.compile(r"(?<![\\A-Za-z0-9_^])([zF])(?![A-Za-z0-9_^(])")
LOGODDS_SUFFIX = "[log-odds]"


def _blank_text_args(seg: str) -> str:
    """``seg`` with the braced argument of each text-like command blanked."""
    out: List[str] = []
    i, n = 0, len(seg)
    while i < n:
        m = re.compile(r"\\([A-Za-z]+)\*?").match(seg, i)
        if m and m.group(1) in SKIP_ARG_COMMANDS:
            j = _skip_group(seg, m.end())
            out.append(" " * (j - i))
            i = j
        else:
            out.append(seg[i])
            i += 1
    return "".join(out)
# Literal Greek characters map to the command they spell.
UNICODE_GREEK = {
    "\u03b1": "alpha", "\u03b2": "beta", "\u03b3": "gamma", "\u03b4": "delta", "\u03b5": "varepsilon",
    "\u03b6": "zeta", "\u03b7": "eta", "\u03b8": "theta", "\u03b9": "iota", "\u03ba": "kappa",
    "\u03bb": "lambda", "\u03bc": "mu", "\u03bd": "nu", "\u03be": "xi", "\u03c0": "pi", "\u03c1": "rho",
    "\u03c3": "sigma", "\u03c4": "tau", "\u03c5": "upsilon", "\u03c6": "phi", "\u03c7": "chi",
    "\u03c8": "psi", "\u03c9": "omega", "\u0393": "Gamma", "\u0394": "Delta", "\u0398": "Theta",
    "\u039b": "Lambda", "\u039e": "Xi", "\u03a0": "Pi", "\u03a3": "Sigma", "\u03a6": "Phi",
    "\u03a8": "Psi", "\u03a9": "Omega", "\u03a5": "Upsilon",
    "\u03d5": "varphi", "\u03f5": "epsilon", "\u03d1": "vartheta",
    "\u03c2": "varsigma", "\u03f0": "varkappa", "\u03f1": "varrho",
    "\u03d6": "varpi",
}

# Precise mode (gha#1159): flag only a Latin or Greek letter that has a
# suggestion above, not every single letter, so index letters such as `k` and
# `p` pass. Off by default; set by LML_MODE=known.
KNOWN_ONLY = False

# Macros the library marks "deprecated, use \x" in interpretations.tsv:
# name (no backslash) -> replacement (with backslash). Loaded from
# LML_DEPRECATED_FILES; a use of one is flagged in either mode.
DEPRECATED: Dict[str, str] = {}
DEPRECATED_RE = re.compile(r"deprecated,\s*use\s+(\\[A-Za-z]+)")

GENERIC_ADVICE = (
    "use the semantic macro for this quantity (see interpretations.tsv in "
    "Morrison-Lab/macros), or put a passage about the notation itself in a "
    "::: {.notation} div"
)

# -- Parsing -----------------------------------------------------------------

# A fence may sit in a blockquote or a list item, at any indent.
FENCE_RE = re.compile(
    r"^[ \t>]*(?:(?:[-*+]|\d+[.)])[ \t]+)?(`{3,}|~{3,})(.*)$"
)
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
ENV_BEGIN_RE = re.compile(
    r"^\s*\\begin\{(" + "|".join(DISPLAY_ENVIRONMENTS) + r")\*?\}"
)
INLINE_MATH_RE = re.compile(r"(?<![\\$])\$(?![\s$])(.+?)(?<![\s\\$])\$(?!\d)")
# A blockquote paragraph that opens with the cross mark is a counter-example of
# what not to write, so its raw letters are the point and are never flagged.
QUOTE_RE = re.compile(r"^\s*((?:>\s*)+)(.*)$")
BAD_EXAMPLE_MARK = "❌"
GOOD_EXAMPLE_MARK = "✅"
NOTATION_CLASS_RE = re.compile(r"(?:^|[\s{])\.?notation(?=[\s}]|$)")
# Anchored to the whole line, so a directive quoted in prose or a code span
# is not obeyed.
DIRECTIVE_RE = re.compile(
    r"^\s*<!--\s*check-literal-math-letters:\s*([a-z-]+)\s*-->\s*$"
)
QUOTED_RE = re.compile(r"\"[^\"]*\"|'[^']*'")


class Finding(NamedTuple):
    line: int
    tokens: Tuple[str, ...]


class Div(NamedTuple):
    length: int
    notation: bool


def _mask_code_spans(line: str) -> str:
    """Blank inline code spans, closed by a backtick run of equal length."""
    out = list(line)
    i, n = 0, len(line)
    while i < n:
        if line[i] != "`":
            i += 1
            continue
        j = i
        while j < n and line[j] == "`":
            j += 1
        run = j - i
        k = j
        close = -1
        while k < n:
            if line[k] == "`":
                m = k
                while m < n and line[m] == "`":
                    m += 1
                if m - k == run:
                    close = k
                    break
                k = m
            else:
                k += 1
        if close < 0:
            i = j
            continue
        for p in range(i, close + run):
            out[p] = " "
        i = close + run
    return "".join(out)


def _mask_html_comments(line: str, in_comment: bool) -> Tuple[str, bool]:
    """Blank HTML comment text (possibly spanning lines), keeping the length."""
    out, i, n = [], 0, len(line)
    while i < n:
        if in_comment:
            end = line.find("-->", i)
            if end < 0:
                out.append(" " * (n - i))
                return "".join(out), True
            out.append(" " * (end + 3 - i))
            i, in_comment = end + 3, False
        else:
            start = line.find("<!--", i)
            if start < 0:
                out.append(line[i:])
                break
            out.append(line[i:start])
            i, in_comment = start, True
    return "".join(out), in_comment


def _skip_group(s: str, i: int) -> int:
    """Index after the balanced ``{...}`` group starting at or after ``i``."""
    n = len(s)
    while i < n and s[i] in " \t":
        i += 1
    if i >= n or s[i] != "{":
        return i
    depth = 0
    while i < n:
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def scan_math(text: str) -> List[str]:
    """Literal letters in one math span, in order, as display tokens.

    A Latin letter is its own token (``y``); a Greek letter is its command
    (``\\theta``).
    """
    stripped = text.lstrip()
    if stripped.startswith(DEFINITION_COMMANDS):
        return []
    tokens: List[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            j = i + 1
            while j < n and text[j].isascii() and text[j].isalpha():
                j += 1
            name = text[i + 1:j]
            if not name:
                i += 2  # `\,` `\\` `\{` and the like
                continue
            if name in GREEK_COMMANDS:
                if not KNOWN_ONLY or name in GREEK_SUGGESTIONS:
                    tokens.append("\\" + name)
            elif name in DEPRECATED:
                tokens.append("\\" + name)
            if name in SKIP_ARG_COMMANDS:
                if j < n and text[j] == "*":
                    j += 1
                env = None
                if name in ("begin", "end"):
                    m = re.match(r"\s*\{([^}]*)\}", text[j:])
                    env = m.group(1) if m else None
                j = _skip_group(text, j)
                if name == "begin" and env in SECOND_ARG_ENVIRONMENTS:
                    j = _skip_group(text, j)
            i = j
        elif c.isascii() and c.isalpha():
            j = i
            while j < n and text[j].isascii() and text[j].isalpha():
                j += 1
            if j - i == 1 and (not KNOWN_ONLY or c in LATIN_SUGGESTIONS):
                tokens.append(c)
            i = j
        elif c in UNICODE_GREEK:
            if not KNOWN_ONLY or UNICODE_GREEK[c] in GREEK_SUGGESTIONS:
                tokens.append("\\" + UNICODE_GREEK[c])
            i += 1
        else:
            i += 1
    return tokens


def load_deprecated(path: str) -> Dict[str, str]:
    """Deprecated macro names from a tab-separated interpretations file.

    A row reads ``\\name<TAB>description``; a description containing
    ``deprecated, use \\other`` marks ``name`` as deprecated in favor of
    ``\\other``. A missing file is reported and yields no rules, so the rest
    of the check still runs.
    """
    found: Dict[str, str] = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for row in handle:
                name, _, description = row.partition("\t")
                match = DEPRECATED_RE.search(description)
                if name.startswith("\\") and match:
                    found[name[1:].strip()] = match.group(1)
    except OSError:
        print(f"::warning::Could not read the deprecated-macro file '{path}'; "
              f"skipping the deprecated-alias rule.")
    return found


def _inline_spans(prose: str) -> List[str]:
    return [m.group(1) for m in INLINE_MATH_RE.finditer(prose)]


def _has_ignore_file(lines: List[str]) -> bool:
    """True if an `ignore-file` directive stands outside any code fence."""
    fence: Optional[Tuple[str, int]] = None
    for raw in lines:
        m = FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        if m:
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        d = DIRECTIVE_RE.match(raw)
        if d and d.group(1) == "ignore-file":
            return True
    return False


def _find_env_end(line: str, env: str) -> int:
    """Index of the exact `\\end{env}` (or starred form), else -1."""
    m = re.search(r"\\end\{" + re.escape(env) + r"\*?\}", line)
    return m.start() if m else -1


def _div_is_notation(attrs: str) -> bool:
    return bool(NOTATION_CLASS_RE.search(QUOTED_RE.sub("", attrs)))


def scan_file(lines: List[str]) -> Tuple[List[Finding], int]:
    """Findings (one per line) and the number of math spans scanned."""
    if _has_ignore_file(lines):
        return [], 0

    findings: List[Finding] = []
    spans = 0
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    in_display = False
    env: Optional[str] = None
    divs: List[Div] = []
    allow_through = 0  # last line number covered by an `allow` directive
    bad_example = False  # inside a blockquote paragraph that opens with a cross mark
    good_example = False  # inside a blockquote paragraph that opens with a check mark
    quote_open = True  # the next quote line opens a paragraph
    quote_depth = 0  # nesting depth of the previous quote line
    start = 0

    if lines and lines[0].strip() == "---":
        for k in range(1, len(lines)):
            if lines[k].strip() in ("---", "..."):
                start = k + 1
                break

    for idx in range(start, len(lines)):
        lineno = idx + 1
        raw = lines[idx]
        if fence is not None:
            m = FENCE_RE.match(raw)
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        m = FENCE_RE.match(raw)
        if m and not in_display and env is None:
            fence = (m.group(1)[0], len(m.group(1)))
            continue

        directive = None if in_comment else DIRECTIVE_RE.match(raw)
        if directive and directive.group(1) == "allow":
            allow_through = lineno + 1

        line, in_comment = _mask_html_comments(raw, in_comment)
        if not line.strip():
            in_display = False
            env = None  # a blank line ends an unclosed environment, as for $$
            bad_example = good_example = False
            quote_open = True
            quote_depth = 0
            continue

        quote = QUOTE_RE.match(line)
        if quote is None or not quote.group(2).strip():
            # a non-quote line or an empty `>` ends the paragraph
            bad_example = good_example = False
            quote_open = True
            quote_depth = 0
        else:
            text = quote.group(2).lstrip()
            depth = quote.group(1).count(">")
            if depth != quote_depth:  # entering or leaving a nested quote
                bad_example = good_example = False
                quote_open = True
            quote_depth = depth
            # a cross mark starts a counter-example only when it opens the
            # paragraph or follows a check-mark paragraph, not in mid-paragraph
            if text.startswith(BAD_EXAMPLE_MARK) and (quote_open or good_example):
                bad_example, good_example = True, False
            elif text.startswith(GOOD_EXAMPLE_MARK):
                bad_example, good_example = False, True
            quote_open = False

        if not in_display and env is None:
            dm = DIV_RE.match(line)
            if dm:
                colons, attrs = len(dm.group(1)), dm.group(2)
                if attrs:
                    divs.append(Div(colons, _div_is_notation(attrs)))
                elif divs:
                    divs.pop()  # Pandoc: any fence line closes the innermost div
                continue

        line = _mask_code_spans(line).replace("\\$", "  ")
        math: List[str] = []

        if env is not None:
            end = _find_env_end(line, env)
            if end < 0:
                math.append(line)
            else:
                math.append(line[:end])
                env = None
        elif not in_display and ENV_BEGIN_RE.match(line):
            name = ENV_BEGIN_RE.match(line).group(1)
            end = _find_env_end(line, name)
            if end < 0:
                math.append(line)
                env = name
            else:
                math.append(line[:end])
        else:
            pos = 0
            while pos <= len(line):
                if in_display:
                    j = line.find("$$", pos)
                    if j < 0:
                        math.append(line[pos:])
                        break
                    math.append(line[pos:j])
                    pos, in_display = j + 2, False
                else:
                    j = line.find("$$", pos)
                    prose = line[pos:] if j < 0 else line[pos:j]
                    math.extend(_inline_spans(prose))
                    if j < 0:
                        break
                    pos, in_display = j + 2, True

        math = [seg for seg in math if seg.strip()]
        if any(d.notation for d in divs) or lineno <= allow_through or bad_example:
            continue
        tokens: List[str] = []
        for seg in math:
            spans += 1
            tokens.extend(scan_math(seg))
        if LOGODDS_CONTEXT_RE.search(line) and not LOGODDS_EXEMPT_RE.search(line):
            for seg in math:
                for lm in LOGODDS_LETTER_RE.finditer(_blank_text_args(seg)):
                    letter = lm.group(1)
                    if letter in tokens:  # the generic token says it already
                        tokens.remove(letter)
                    tokens.append(letter + LOGODDS_SUFFIX)
        if tokens:
            findings.append(Finding(lineno, tuple(tokens)))
    return findings, spans


# -- Messages ----------------------------------------------------------------

def _describe(token: str) -> str:
    if token.startswith("\\") and token[1:] in DEPRECATED:
        return f"{token} is deprecated -> {DEPRECATED[token[1:]]}"
    if token.endswith(LOGODDS_SUFFIX):
        letter = token[0]
        return (f"{letter} -> \\logodds if this is the log-odds "
                f"(the course symbol is eta, not {letter})")
    if token.startswith("\\"):
        suggestion = GREEK_SUGGESTIONS.get(token[1:])
    else:
        suggestion = LATIN_SUGGESTIONS.get(token)
    return f"{token} -> {suggestion}" if suggestion else token


def format_message(tokens: Tuple[str, ...]) -> str:
    seen: List[str] = []
    for token in tokens:
        if token not in seen:
            seen.append(token)
    shown = "; ".join(_describe(t) for t in seen[:8])
    more = f"; and {len(seen) - 8} more" if len(seen) > 8 else ""
    return (f"Literal letter(s) or deprecated macro(s) in math: {shown}{more}. "
            f"Fix: {GENERIC_ADVICE}")


# -- Git plumbing ------------------------------------------------------------

def _run_git(args: List[str]) -> Optional[str]:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    return res.stdout if res.returncode == 0 else None


_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_diff(diff: str) -> Tuple[Dict[str, Dict[int, str]], Set[str]]:
    """Added ``{path: {line_number: text}}`` and the set of deleted texts.

    Hunk header counts decide where a hunk ends, so an added line that begins
    with two plus signs is never mistaken for a ``+++`` file header.
    """
    added: Dict[str, Dict[int, str]] = {}
    deleted: Set[str] = set()
    path: Optional[str] = None
    old_left = new_left = new_line = 0
    for line in diff.splitlines():
        if old_left > 0 or new_left > 0:
            if line.startswith("+"):
                if path is not None:
                    added[path][new_line] = line[1:]
                new_line += 1
                new_left -= 1
            elif line.startswith("-"):
                deleted.add(line[1:])
                old_left -= 1
            continue
        if line.startswith("+++ "):
            target = line[4:].rstrip("\t")
            path = None if target == "/dev/null" else target[2:] if target.startswith("b/") else target
            if path is not None:
                added.setdefault(path, {})
            continue
        m = _HUNK_RE.match(line)
        if m:
            old_left = int(m.group(1)) if m.group(1) is not None else 1
            new_line = int(m.group(2))
            new_left = int(m.group(3)) if m.group(3) is not None else 1
    return added, deleted


def _glob_to_regex(pat: str) -> "re.Pattern[str]":
    """Translate a path glob to an anchored regex; supports ``**``, ``*``, ``?``."""
    i, n, out = 0, len(pat), []
    while i < n:
        c = pat[i]
        if c == "*":
            if pat[i:i + 2] == "**":
                i += 2
                if pat[i:i + 1] == "/":
                    out.append("(?:.*/)?")
                    i += 1
                else:
                    out.append(".*")
            else:
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def compile_ignores(patterns: List[str]) -> List["re.Pattern[str]"]:
    compiled = []
    for pat in patterns:
        compiled.append(_glob_to_regex(pat))
        if "*" not in pat and "?" not in pat:
            compiled.append(_glob_to_regex(pat.rstrip("/") + "/**"))
    return compiled


def _ignored(rel: str, ignores: List["re.Pattern[str]"]) -> bool:
    return any(r.match(rel) for r in ignores)


def _split_list(value: str) -> List[str]:
    return [p.strip() for p in re.split(r"[,\n]", value) if p.strip()]


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
    files: int
    lines: int
    spans: int
    skipped: bool


def _read_lines(path: str) -> Optional[List[str]]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().split("\n")
    except OSError:
        return None
    if lines and lines[-1] == "":
        lines.pop()  # the newline ending the file does not start a line
    return lines


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    """Scan the added lines since ``base_ref``, or every line when whole-tree."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = _run_git(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, 0, 0, True)
        for rel in out.splitlines():
            if rel and not _ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, 0, True)
        base = _run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, 0, True)
        diff = _run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                         base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, 0, True)
        added, deleted = parse_diff(diff)
        for rel, numbered in added.items():
            if _ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if not (text.strip() and text in deleted)}

    findings: List[Tuple[str, Finding]] = []
    files = lines = spans = 0
    for rel in sorted(wanted):
        content = _read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        file_findings, file_spans = scan_file(content)
        spans += file_spans
        for finding in file_findings:
            if keep is None or finding.line in keep:
                findings.append((rel, finding))
    return Report(findings, files, lines, spans, False)


def main() -> int:
    base_ref = os.environ.get("LML_BASE_REF", "").strip()
    globs = os.environ.get("LML_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("LML_PATHS_IGNORE", "")))
    fail = _env_flag("LML_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("LML_WHOLE_TREE", False)

    global KNOWN_ONLY
    mode = os.environ.get("LML_MODE", "all").strip().lower() or "all"
    if mode not in ("all", "known"):
        print(f"::error::LML_MODE must be 'all' or 'known', not '{mode}'.")
        return 2
    KNOWN_ONLY = mode == "known"
    for path in os.environ.get("LML_DEPRECATED_FILES", "").split():
        DEPRECATED.update(load_deprecated(path))

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        # With no base-ref (a push run) the skip is expected, so it is not an annotation.
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the literal-math-letters check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every literal letter the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s), "
        f"{report.spans} math span(s) (scope: {scope})."
    )
    if not report.findings:
        print("No literal letters in math.")
        return 0

    severity = "error" if fail else "warning"
    for rel, finding in report.findings:
        print(f"::{severity} file={rel},line={finding.line}::"
              f"{format_message(finding.tokens)}")
    print(f"\n{len(report.findings)} line(s) carry literal letters in math.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
