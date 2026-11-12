#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag an exercise whose title names an object that the body never mentions.

The lab's rule (Ezra, 2026-10-29; Morrison-Lab/psw teaching chapter): an
exercise body gives the background its title implies. If the title says
"Maximizing a gamma-family kernel", the body says what a gamma distribution
and its kernel are, links them, and says why anyone cares. This check covers
only the first step, naming the object: it cannot tell whether the body
links or explains it, so a pass does not mean the background is adequate.

What is flagged: an exercise div (id ``exr-...``) with a heading title or a
``title="..."`` attribute that names a defined term (a phrase from some
``#def-`` title in the scanned files) whose words the body never uses. Only a
run of title words that matches a whole defined phrase is judged, so "times"
is not read as part of "time series". A title naming aliases ("Gradient (also
called del)") defines each one.

What counts as the body (gha#1481): the exercise's own text without nested
solution divs (``#sol-``, ``.sol``, ``.solution``, ``.answer``), plus the
text of every div it cites or links (``@exr-``, ``@def-``, ``@thm-``,
``@sol-``, ``#def-...`` and the rest), followed transitively. A cited
exercise lends its text but not its solutions. An exercise that cites an
``exr-`` the scanned files do not hold is skipped, since its background is
elsewhere. A part that builds on an earlier exercise ("Use the setup of
@exr-...") is skipped too. A math macro says the word its name begins
with (``\grad`` says gradient), short macros say the words ``MACRO_WORDS`` lists
(``\E`` says expected), and words inside ``\text{}``, ``\operatorname{}`` and
``\mathrm{}`` count as body words.

A word counts as present when another word in the body shares its first
five letters, so "Maximizing" matches "maximum". Generic task verbs (find,
compute, expand, classify, ...) are never reported. Math in the title, code
fences and HTML comments are ignored.

Whole-tree runs on lds, mds, pds, sds, and psw (gha#1481) left only titles
that name a term the body never states, so the check fails by default.
A title word that the body expresses only with a synonym or with notation is
still reported: say the word in the body, with its link, or reword the title.

Diff-scoped like check-bare-yes-no: a finding is reported only when the diff
adds a line of the exercise, an untouched exercise keeps its form, and with no
base ref the check skips rather than scanning the whole tree.
``EXB_WHOLE_TREE=true`` measures a corpus. Needs Python 3.9 or later.

Configuration (environment variables, set by the composite action):
  EXB_BASE_REF    Git ref/SHA to diff against. Empty and not whole-tree => skip.
  EXB_GLOBS       Space-separated git pathspecs (default: '*.qmd').
  EXB_FAIL        default "true" => exit 1 on a finding; "false" => warnings.
  EXB_WHOLE_TREE  "true" => scan every tracked matching file in full.
"""

import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402

DEFAULT_GLOBS = "*.qmd"
DEFAULT_FAIL = True
ADVICE = ("say it in the body and link its definition, "
          "or reword the title; give the background the title implies")

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
EXR_RE = re.compile(r"#exr-")
DEF_RE = re.compile(r"#def-")
# A later part of an exercise builds on the setup of an earlier exercise, which
# gives the background; the part itself need not repeat it.
CONTINUATION_RE = re.compile(r"\b(?:setup|set-up|situation|model|data) of @exr-|^\s*Use (?:the )?\w+ of @exr-",
                             re.MULTILINE)
# A cross-reference or link to another div brings that div's text in as
# background (gha#1481): citing a definition or an earlier exercise is how a
# body gives the background a title names.
REF_RE = re.compile(r"(?:@|#)(exr-[\w-]*\w)|(?:@|#)((?:thm|lem|prp|cor|exm|def|sol)-[\w-]*\w)")
ID_RE = re.compile(r"#((?:exr|thm|lem|prp|cor|exm|def|sol)-[\w-]*\w)")
MACRO_RE = re.compile(r"\\([A-Za-z]+)")
# Short macros whose name is not a prefix of the word they print (gha#1481).
MACRO_WORDS = {
    "e": "expected expectation", "ep": "expected expectation",
    "pr": "probability", "prf": "probability", "hpr": "probability",
    "p": "probability", "sqf": "squared square", "ndist": "normal gaussian",
    "dprod": "dot product", "tprod": "product", "deriv": "derivative",
    "derivf": "derivative partial", "dif": "derivative", "difs": "derivative",
    "sigmoid": "logistic", "exp": "exponential", "log": "log logarithm",
    "int": "integral", "var": "variance", "cov": "covariance",
    "max": "maximum", "min": "minimum", "sum": "sum summation",
    "det": "determinant", "lim": "limit", "dim": "dimension",
    "ker": "kernel", "sin": "sine", "cos": "cosine", "tan": "tangent",
}
# Commands that format math rather than name a concept (gha#1481).
TYPESETTING_MACROS = frozenset("""
    text textrm textit textbf textsf texttt operatorname mathrm mathbf mathit
    mathsf mathtt mathbb mathcal mathfrak boldsymbol left right bigl bigr
    begin frac dfrac tfrac sqrt overline underline widehat widetilde
    quad qquad cdot cdots ldots dots label nonumber displaystyle
""".split())
# Words a math span prints as text, such as \operatorname{softmax}.
TEXT_ARG_RE = re.compile(r"\\(?:text|textrm|textit|operatorname|mathrm)\{([^{}]*)\}")
SOL_RE = re.compile(r"#sol-|\.(?:sol|solution|answer)(?![\w-])")
ATTR_TITLE_RE = re.compile(r'title="([^"]*)"')
TITLE_RE = re.compile(r"^#{1,6}\s+(.*?)\s*(?:\{[^}]*\})?\s*$")
MATH_RE = re.compile(r"\$[^$]*\$")
LINK_RE = re.compile(r"\]\([^)]*\)")
WORD_RE = re.compile(r"[a-z]+")
STEM = 5

# Task verbs and connecting words that a title may use without the body
# repeating them.
GENERIC = frozenset("""
    about above after again against also another answer apply approximate
    ask assess based before below between both calculate change check choose
    classify compare compute conclude confirm connect consider construct
    count decide define demonstrate derive describe determine differentiate
    does each estimate evaluate every example exercise expand explain express
    extend find first from give given having how identify implement
    include interpret into justify list make many match more most name
    need other over part plot predict prove read recognize relate rewrite
    same say second see select show simplify solve some state step steps
    still such take test than that their them then there these they this
    those three through time under until use used using value values
    verify what when where whether which while whose will with within
    without work write your
""".split())


GENERIC_STEMS = frozenset(w[:STEM] for w in GENERIC)


class Finding(NamedTuple):
    line: int
    title: str
    missing: List[str]
    start: int
    end: int


POSSESSIVE_RE = re.compile(r"['’]s\b", re.I)


def _words(text: str) -> List[str]:
    text = MATH_RE.sub(" ", text)
    text = LINK_RE.sub("]", text)
    text = POSSESSIVE_RE.sub("", text)
    return WORD_RE.findall(text.lower())


def _stems(words: List[str]) -> Set[str]:
    return {w[:STEM] for w in words if len(w) >= 3}


# Word endings whose singular and plural are the same (gha#1481).
INVARIANT_PLURALS = ("series", "species")


def _singular(word: str) -> str:
    """The singular of an English plural, or ``word`` unchanged.

    "probabilities" gives "probability", "processes" and "boxes" drop "es",
    "biases" gives "bias", and a word ending in "ss", "us", "is" or "as"
    ("loss", "radius", "analysis", "bias") is left alone, as is a word ending
    in "series" or "species" ("subspecies").
    """
    if (len(word) <= 3 or not word.endswith("s")
            or word.endswith(INVARIANT_PLURALS)):
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("sses", "xes", "ches", "shes", "zzes", "iases")):
        return word[:-2]
    if word.endswith(("ss", "us", "is", "as")):
        return word
    return word[:-1]


# An alias marker is matched with the adverb that may lead it ("often
# called"), so the adverb is not read as a term of its own.
PHRASE_SPLIT_RE = re.compile(
    r"[(),;:/]"
    r"|\b(?:also|often|sometimes|usually|commonly|simply)\s+"
    r"(?:called|known\s+as|named)\b"
    r"|\bcalled\b|\bknown\s+as\b|\balso\b",
    re.I,
)
OR_RE = re.compile(r"\bor\b", re.I)
LEADING_OR_RE = re.compile(r"^\s*or\b", re.I)
MAX_PHRASE = 6
ARTICLES = {"a", "an", "the"}


def _phrase_words(part: str) -> List[str]:
    words = [_singular(w) for w in _words(part)]
    while words and words[0] in ARTICLES:
        words = words[1:]
    return words


def _phrases(title: str) -> Set[str]:
    """The defined terms a ``#def-`` title names, each as singular words.

    A title such as "Gradient (also called del)" names two terms, so it is
    split at parentheses, commas, semicolons and alias markers such as
    "called" or "often known as", in any letter case, and a leading article
    is dropped. Math is removed first, so the comma in ``$(X, Y)$`` splits
    nothing. A part's leading "or" is dropped ("Gradient (or del)"), and an
    "or" inside a part splits it only where words stand on both sides, so
    "Loss or cost" names two terms and "Exclusive or" one.
    """
    out: Set[str] = set()
    for part in PHRASE_SPLIT_RE.split(MATH_RE.sub(" ", title)):
        part = LEADING_OR_RE.sub("", part)
        pieces = [_phrase_words(piece) for piece in OR_RE.split(part)]
        if not all(pieces):
            pieces = [_phrase_words(part)]
        for words in pieces:
            if 0 < len(words) <= MAX_PHRASE:
                out.add(" ".join(words))
    return out


def defined_stems(lines: List[str]) -> Set[str]:
    """The terms the ``#def-`` divs in ``lines`` define, as phrases.

    A title word is judged only where the exercise title names a whole defined
    term (gha#1481). Matching single words by their first letters had read
    "times" as part of "time series", "point" as part of "critical point" and
    "weigh" as part of "weight"; matching whole phrases does not.
    """
    stems: Set[str] = set()
    for idx, raw in enumerate(lines):
        dm = DIV_RE.match(raw)
        if not (dm and dm.group(2) and DEF_RE.search(dm.group(2))):
            continue
        attr_title = ATTR_TITLE_RE.search(dm.group(2))
        if attr_title:
            stems |= _phrases(attr_title.group(1))
            continue
        for follow in lines[idx + 1:idx + 4]:
            tm = TITLE_RE.match(follow)
            if tm:
                stems |= _phrases(tm.group(1))
                break
    return stems


def macro_words(body: str) -> List[str]:
    """Words that the math macros in ``body`` print, for matching a title.

    A macro counts as the word its name begins with: ``\\grad`` says gradient
    and ``\\noise`` says noise. Names shorter than four letters only count
    through ``MACRO_WORDS``, since as prefixes ``\\sim`` and ``\\int`` would
    say "simple" and "interval". Typesetting commands such as ``\\text`` and
    ``\\operatorname`` say no word of their own.
    """
    out: List[str] = []
    for arg in TEXT_ARG_RE.findall(body):
        out.extend(w.lower() for w in WORD_RE.findall(arg.lower()))
    for name in MACRO_RE.findall(body):
        low = name.lower()
        out.extend(MACRO_WORDS.get(low, "").split())
        if len(low) >= 4 and low not in TYPESETTING_MACROS:
            out.append(low)
    return out


def missing_words(title: str, body: str,
                  defined: Optional[Set[str]] = None) -> List[str]:
    """Content words of ``title`` with no counterpart in ``body``.

    With ``defined`` given, only a word that is a defined term (a word in the
    title of some ``#def-`` div) is reported: the rule is about the background
    of technical terms, and an ordinary word needs none.
    """
    present = _stems(_words(body))
    macros = macro_words(body)
    words = _words(title)
    singulars = [_singular(w) for w in words]
    named = set(range(len(words)))
    if defined is not None:
        named = set()
        for i in range(len(words)):
            for n in range(1, MAX_PHRASE + 1):
                if i + n <= len(words) and " ".join(singulars[i:i + n]) in defined:
                    named.update(range(i, i + n))
    # A three-letter word ("del") is judged only as part of a defined term:
    # without definitions, short title words are mostly noise.
    min_len = 3 if defined is not None else 4
    out: List[str] = []
    for idx, word in enumerate(words):
        if len(word) < min_len or word[:STEM] in GENERIC_STEMS:
            continue
        if idx not in named:
            continue
        if (word[:STEM] in present or singulars[idx][:STEM] in present
                or word in out):
            continue
        if any(word.startswith(m[:STEM]) for m in macros):
            continue
        out.append(word)
    return out


def div_texts(lines: List[str]) -> Dict[str, str]:
    """The text of each div with a cross-reference id in ``lines``, by id.

    An exercise's text is its title and body without solutions, the background
    a later exercise that cites it can lean on.
    """
    texts: Dict[str, str] = {}
    stack: List[Tuple[Optional[str], bool, List[str]]] = []
    fence: Optional[str] = None
    for raw in lines:
        fm = FENCE_RE.match(raw)
        if fence is not None:
            if fm and fm.group(1)[0] == fence:
                fence = None
            continue
        if fm:
            fence = fm.group(1)[0]
            continue
        dm = DIV_RE.match(raw)
        if dm:
            if dm.group(2):
                im = ID_RE.search(dm.group(2))
                title = ATTR_TITLE_RE.search(dm.group(2))
                buf = [title.group(1)] if title else []
                sol = bool(SOL_RE.search(dm.group(2)))
                stack.append((im.group(1) if im else None, sol, buf))
            elif stack:
                ident, sol, buf = stack.pop()
                text = "\n".join(buf)
                if ident:
                    texts[ident] = text
                if not sol:
                    for _, _, outer in stack[-1:]:
                        outer.append(text)
            continue
        for _, _, buf in stack[-1:]:
            buf.append(raw)
    return texts


def background(body: str, index: Dict[str, str],
               own: Optional[str] = None) -> Optional[str]:
    """The text of the divs ``body`` builds on, followed transitively.

    Returns None when ``body`` cites an exercise ``index`` does not hold:
    its background is elsewhere, so no title word can be judged missing.
    """
    seen: Set[str] = {own} if own else set()
    parts: List[str] = []
    todo = [body]
    while todo:
        for exr, other in REF_RE.findall(todo.pop()):
            ident = exr or other
            if ident in seen:
                continue
            seen.add(ident)
            if ident not in index:
                if exr:
                    return None
                continue
            parts.append(index[ident])
            todo.append(index[ident])
    return "\n".join(parts)


def exercises(lines: List[str], defined: Optional[Set[str]] = None,
              index: Optional[Dict[str, str]] = None) -> List[Finding]:
    """Each exercise div whose title has a defined term its body never uses."""
    if index is None:
        index = div_texts(lines)
    found: List[Finding] = []
    fence: Optional[str] = None
    in_comment = False
    depth = 0
    cur: Optional[Dict] = None
    for idx, raw in enumerate(lines):
        lineno = idx + 1
        if in_comment:
            in_comment = "-->" not in raw
            continue
        if raw.lstrip().startswith("<!--"):
            in_comment = "-->" not in raw
            continue
        fm = FENCE_RE.match(raw)
        if fence is not None:
            if fm and fm.group(1)[0] == fence:
                fence = None
            continue
        if fm:
            fence = fm.group(1)[0]
            continue
        dm = DIV_RE.match(raw)
        if dm:
            if dm.group(2):
                attrs = dm.group(2)
                if cur is None and EXR_RE.search(attrs):
                    attr_title = ATTR_TITLE_RE.search(attrs)
                    own_id = re.search(r"#(exr-[\w-]+)", attrs)
                    cur = {"depth": depth, "start": lineno, "skip": None,
                           "title": attr_title.group(1) if attr_title else None,
                           "title_line": lineno, "body": [],
                           "id": own_id.group(1) if own_id else None}
                elif cur is not None:
                    if cur["skip"] is None and SOL_RE.search(attrs):
                        cur["skip"] = depth
                    if cur["skip"] is None:
                        cur["body"].append(raw)
                depth += 1
            elif depth > 0:
                depth -= 1
                if cur is not None and depth == cur["depth"]:
                    missing = []
                    body = "\n".join(cur["body"])
                    extra = background(body, index, cur["id"])
                    if (cur["title"] and extra is not None
                            and not CONTINUATION_RE.search(body)):
                        missing = missing_words(cur["title"], body + "\n" + extra,
                                                defined)
                    if missing:
                        found.append(Finding(cur["title_line"], cur["title"], missing,
                                             cur["start"], lineno))
                    cur = None
                elif cur is not None:
                    if cur["skip"] == depth:
                        cur["skip"] = None
                    elif cur["skip"] is None:
                        cur["body"].append(raw)
            continue
        if cur is None or cur["skip"] is not None:
            continue
        tm = TITLE_RE.match(raw)
        if tm and cur["title"] is None and not any(b.strip() for b in cur["body"]):
            cur["title"] = tm.group(1)
            cur["title_line"] = lineno
            continue
        cur["body"].append(raw)
    return found


def added_lines(diff: str) -> Dict[str, Set[int]]:
    """Added line numbers per path from ``git diff -U0`` output."""
    added, _deleted = diffscope.parse_diff(diff)
    return {path: set(lines) for path, lines in added.items()}


def wanted_lines(base_ref: str, globs: List[str], whole_tree: bool
                 ) -> Optional[Dict[str, Optional[Set[int]]]]:
    """Files to scan, each with its added lines (None = every line)."""
    if whole_tree:
        paths = diffscope.git_paths(["ls-files", "--", *globs])
        return None if paths is None else {p: None for p in paths}
    if not base_ref:
        return None
    base = diffscope.run_git(["merge-base", base_ref, "HEAD"])
    if not base or not base.strip():
        return None
    diff = diffscope.run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                              base.strip(), "--", *globs])
    return None if diff is None else dict(added_lines(diff))


def corpus(globs: List[str]) -> Tuple[Set[str], Dict[str, str]]:
    """Defined-term stems, and the text of each cross-referenced div, from
    every tracked file the globs match."""
    paths = diffscope.git_paths(["ls-files", "--", *globs]) or []
    stems: Set[str] = set()
    index: Dict[str, str] = {}
    for rel in paths:
        try:
            with open(rel, encoding="utf-8", errors="replace") as handle:
                lines = handle.read().split("\n")
        except OSError:
            continue
        stems |= defined_stems(lines)
        index.update(div_texts(lines))
    return stems, index


def touched(finding: Finding, keep: Optional[Set[int]]) -> bool:
    """Whether the diff adds a line of the exercise."""
    if keep is None:
        return True
    return any(finding.start <= n <= finding.end for n in keep)


def main() -> int:
    base_ref = os.environ.get("EXB_BASE_REF", "").strip()
    globs = os.environ.get("EXB_GLOBS", DEFAULT_GLOBS).split() or [DEFAULT_GLOBS]
    fail = diffscope.env_flag("EXB_FAIL", DEFAULT_FAIL)
    whole = diffscope.env_flag("EXB_WHOLE_TREE", False)
    wanted = wanted_lines(base_ref, globs, whole)
    if wanted is None:
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the exercise background check for this run "
              f"({'could not diff against ' + repr(base_ref) if base_ref else 'no base-ref given'}).")
        return 0
    severity = "error" if fail else "warning"
    findings = 0
    defined, index = corpus(globs)
    if not defined:
        print("::notice::No #def- titles found in the scanned files, so no title word can be "
              "reported as a defined term; the check reports nothing.")
    for rel in sorted(wanted):
        try:
            with open(rel, encoding="utf-8", errors="replace") as handle:
                lines = handle.read().split("\n")
        except OSError:
            continue
        for item in exercises(lines, defined, index):
            if touched(item, wanted[rel]):
                findings += 1
                words = ", ".join(item.missing)
                print(f"::{severity} file={rel},line={item.line}::Exercise title "
                      f"'{item.title[:50]}' uses {words}, which the body never "
                      f"mentions. Fix: {ADVICE}")
    print(f"Examined {len(wanted)} file(s); {findings} exercise(s) flagged.")
    return 1 if findings and fail else 0


if __name__ == "__main__":
    sys.exit(main())
