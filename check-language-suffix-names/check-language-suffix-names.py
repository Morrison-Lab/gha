#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a name with a language suffix (``_py``, ``_r``, ``_jl``) that a pull
request assigns in a code chunk.

The lab's rule (Ezra, on Morrison-Lab/lds#3146): "i thought we agreed not to
use language specific variable names".  A page that shows the same step in R,
Python and Julia gives each language's object the same name, so the tabs read
as one example; a name never carries the language it is written in.
Morrison-Lab/lds#2282 had removed ``_py`` and ``_r`` suffixes from one lab,
and with no check a new chunk copied them back from its neighbours
(Morrison-Lab/lds#3152).

What is read:

- every executable ``{r}``, ``{python}`` and ``{julia}`` chunk of a ``.qmd``,
  ``.Rmd`` or ``.md`` file (a plain ``r`` fence, shown as text, is not read);
- a whole ``.R``, ``.py`` or ``.jl`` file, when ``CLN_GLOBS`` names one.

What is flagged there: a name ending in a suffix from ``CLN_SUFFIXES``
(default ``_py _r _jl``) that a line binds:

- an assignment target: ``x_py = 1``, ``x_r <- 1``, ``x_r <<- 1``,
  ``a_py, b = f()``, ``(a, b_py) = f()``, ``x_py: int = 1``, ``x_py += 1``,
  ``global x_jl = 1``, ``const x_jl = 1``;
- the target of R's right assignment, ``f() -> x_r``;
- a loop variable: ``for x_py in xs``, ``for (i_r in xs)``, ``for i_jl = 1:n``;
- a definition: ``def f_py(``, ``class A_py``, ``function f_jl(``, Julia's
  short form ``f_jl(x) = ...``;
- Python's ``as`` and walrus forms: ``import numpy as np_py``,
  ``with open(p) as f_py``, ``(n_py := len(x))``.

What is not flagged:

- a use of an existing name (``print(x_py)``), which the rename sweep owns;
- an element or attribute assignment, ``x_py[0] = 1``, ``obj.x_py = 1``;
- a keyword argument, ``f(n_py = 1)``;
- a name inside a string or a comment;
- a line carrying, or following a comment-only line that carries,
  ``# check-language-suffix-names: allow: <reason>``.  The reason is
  required: a bare ``allow`` exempts nothing.

Design notes, in the model of ``check-r-head``:

- **Diff-scoped by default.** A line is reported when a PR adds it, so
  existing pages never block.  An added line whose exact text was also
  deleted in the same diff is treated as moved.
  ``CLN_WHOLE_TREE=true`` scans everything, to measure a corpus.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning instead of scanning the whole tree.
- **Blocks by default** (``CLN_FAIL`` defaults to true).
- **The search space is reported.** Every run prints how many files and lines
  it examined.

Configuration (environment variables, set by the composite action):
  CLN_BASE_REF     Git ref/SHA to diff against. Empty and not whole-tree =>
                   skip the check.
  CLN_GLOBS        Space-separated git pathspecs.
  CLN_SUFFIXES     Space- or comma-separated suffixes, matched case-sensitively.
  CLN_PATHS_IGNORE Comma/newline-separated glob patterns to skip (``*``,
                   ``?`` and recursive ``**``).
  CLN_FAIL         "false" => warn only.
  CLN_WHOLE_TREE   "true" => scan every tracked matching file in full.
"""

import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402
import mdmask  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd *.Rmd *.md"
DEFAULT_SUFFIXES = "_py _r _jl"
_DEFAULT_FAIL = True

BACKSLASH = chr(92)

# An executable chunk's info string: ``{r}``, ``{r label}``, ``{python}``,
# ``{julia, echo=false}``.  ``{{r}}`` (shown as text) and ``{rcpp}`` are not.
CHUNK_RE = re.compile(r"^\{\s*(r|R|python|julia)(?![\w.])")

# A script file's language, by extension.
SCRIPT_LANGUAGES = {".r": "r", ".py": "python", ".jl": "julia"}

# A name: R allows dots, Julia a trailing ``!``.
NAME = r"\.?[^\W\d][\w.]*!?"
NAME_RE = re.compile(NAME)

# The allow comment needs a reason after ``allow:``.
ALLOW_RE = re.compile(r"#.*\bcheck-language-suffix-names:\s*allow:\s*\S")

# An assignment operator.  ``=`` but not ``==``, ``<=``, ``>=``, ``!=`` or a
# keyword argument (excluded later, since the prefix then holds a bracket).
ASSIGN_OP_RE = re.compile(
    r"<<-|<-|:=|\*\*=|//=|>>=|<<=|[-+*/%&|^@]=|(?<![=<>!~:.])=(?!=)")

# A prefix made only of assignment targets: ``a``, ``a, b``, ``(a, *b)``.
TARGETS_RE = re.compile(
    r"[(\[]?\s*\*?(" + NAME + r")(?:\s*,\s*\*?(" + NAME + r"))*\s*,?\s*[)\]]?")

# Julia's declaration keywords before a target.
DECLARE_RE = re.compile(r"^(?:(?:global|local|const)\s+)+")

RIGHT_ASSIGN_RE = re.compile(r"->>?\s*(" + NAME + r")\s*(?:;|$)")
FOR_RE = re.compile(
    r"\bfor\s*\(?\s*\(?\s*(" + NAME + r"(?:\s*,\s*" + NAME + r")*)\s*\)?"
    r"\s*(?:\bin\b|=|∈)")
DEF_RE = re.compile(r"^\s*(?:async\s+)?(?:def|class|function|macro|struct|"
                    r"mutable\s+struct)\s+(" + NAME + r")")
JULIA_SHORT_DEF_RE = re.compile(r"^\s*(" + NAME + r")\s*\([^()]*\)\s*=(?!=)")
AS_RE = re.compile(r"\bas\s+(" + NAME + r")")
WALRUS_RE = re.compile(r"(" + NAME + r")\s*:=")


class Finding(NamedTuple):
    line: int
    name: str
    suffix: str


def strip_code_line(line: str) -> str:
    """``line`` with string contents blanked and its ``#`` comment cut.

    Strings are ``"..."``, ``'...'`` and backtick names; a backslash escapes
    the next character.  A string left open at the end of the line is blanked
    to the end (a multi-line string is a stated limitation).
    """
    out: List[str] = []
    quote: Optional[str] = None
    escaped = False
    for ch in line:
        if quote is not None:
            if escaped:
                escaped = False
                out.append(" ")
            elif ch == BACKSLASH:
                escaped = True
                out.append(" ")
            elif ch == quote:
                quote = None
                out.append(ch)
            else:
                out.append(" ")
            continue
        if ch == "#":
            break
        if ch in "\"'`":
            quote = ch
        out.append(ch)
    return "".join(out)


def first_top_level(code: str, pattern: "re.Pattern[str]") -> Optional["re.Match[str]"]:
    """The first match of ``pattern`` at bracket depth 0, else None."""
    depth = 0
    for i, ch in enumerate(code):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0:
            m = pattern.match(code, i)
            if m:
                return m
    return None


def assignment_targets(code: str) -> List[str]:
    """Names a left assignment on ``code`` binds, else an empty list."""
    m = first_top_level(code, ASSIGN_OP_RE)
    if m is None:
        # A parenthesized target list puts its ``=`` at depth 0 only after
        # the closing bracket, which first_top_level already handles; a
        # ``:=`` inside brackets is the walrus, read separately.
        return []
    prefix = DECLARE_RE.sub("", code[:m.start()].strip())
    if m.group(0) == ":=":
        return []
    annotation = first_top_level(prefix, re.compile(r":"))
    if annotation is not None:
        prefix = prefix[:annotation.start()].strip()
    if not TARGETS_RE.fullmatch(prefix):
        return []
    return NAME_RE.findall(prefix)


def bound_names(code: str, language: str) -> List[str]:
    """Names that one stripped line of ``language`` code binds."""
    names = assignment_targets(code)
    names += RIGHT_ASSIGN_RE.findall(code) if language == "r" else []
    for m in FOR_RE.finditer(code):
        names += NAME_RE.findall(m.group(1))
    m = DEF_RE.match(code)
    if m:
        names.append(m.group(1))
    if language == "julia":
        m = JULIA_SHORT_DEF_RE.match(code)
        if m:
            names.append(m.group(1))
    if language == "python":
        names += AS_RE.findall(code)
        names += WALRUS_RE.findall(code)
    if language != "r":
        # Only R names hold a dot; elsewhere ``obj.x_py`` is an attribute.
        names = [name for name in names if "." not in name]
    return names


def suffix_of(name: str, suffixes: List[str]) -> Optional[str]:
    """The suffix ``name`` ends in, when something precedes it, else None."""
    bare = name.rstrip("!")
    for suffix in suffixes:
        if bare.endswith(suffix) and bare[:-len(suffix)].strip("_."):
            return suffix
    return None


def scan_code(lines: List[Tuple[int, str]], language: str,
              suffixes: List[str]) -> List[Finding]:
    """Findings in ``(line number, text)`` pairs of one language's code."""
    found: List[Finding] = []
    previous_allows = False
    for number, raw in lines:
        allows = bool(ALLOW_RE.search(raw))
        code = strip_code_line(raw)
        if not code.strip():
            previous_allows = allows
            continue
        exempt = allows or previous_allows
        previous_allows = False
        if exempt:
            continue
        seen: Set[str] = set()
        for name in bound_names(code, language):
            suffix = suffix_of(name, suffixes)
            if suffix and name not in seen:
                seen.add(name)
                found.append(Finding(number, name, suffix))
    return found


def scan_markdown(lines: List[str], suffixes: List[str]
                  ) -> Tuple[List[Finding], int]:
    """``([Finding, ...], lines examined)`` for a Markdown-family file."""
    found: List[Finding] = []
    fence: Optional[Tuple[str, int, Optional[str]]] = None  # marker, length, language
    chunk: List[Tuple[int, str]] = []
    in_comment = False
    for number, raw in enumerate(lines, 1):
        m = mdmask.FENCE_RE.match(raw)
        if fence is None:
            if m and not in_comment:
                engine = CHUNK_RE.match(m.group(2))
                language = engine.group(1).lower() if engine else None
                fence = (m.group(1)[0], len(m.group(1)), language)
                continue
            # HTML comments are tracked so a fence inside one opens nothing.
            _, in_comment = mdmask.mask_markdown_line(raw, in_comment)
            continue
        if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                and not m.group(2):
            if fence[2]:
                found += scan_code(chunk, fence[2], suffixes)
            chunk = []
            fence = None
            continue
        if fence[2]:
            chunk.append((number, raw))
    if fence is not None and fence[2]:
        found += scan_code(chunk, fence[2], suffixes)
    return found, len(lines)


def scan_file(rel: str, lines: List[str], suffixes: List[str]
              ) -> Tuple[List[Finding], int]:
    """Findings for one file, read as a script or as Markdown by extension."""
    language = SCRIPT_LANGUAGES.get(os.path.splitext(rel)[1].lower())
    if language:
        return scan_code(list(enumerate(lines, 1)), language, suffixes), len(lines)
    return scan_markdown(lines, suffixes)


LANGUAGE_NAMES = {"_py": "Python", "_r": "R", "_jl": "Julia"}


def format_message(finding: Finding) -> str:
    language = LANGUAGE_NAMES.get(finding.suffix, "a language")
    return (f"'{finding.name}' carries the language suffix "
            f"'{finding.suffix}'. Give the {language} object the same name "
            "as its counterpart in the other languages, without a suffix, "
            "so the tabs read as one example. Existing names are left to a "
            "separate rename.")


def split_words(value: str) -> List[str]:
    """Words of a space- or comma-separated list."""
    return [word for word in re.split(r"[\s,]+", value.strip()) if word]


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
    files: int
    lines: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool, suffixes: Optional[List[str]] = None) -> Report:
    """Scan the added lines since ``base_ref``, or every line when whole-tree."""
    suffixes = DEFAULT_SUFFIXES.split() if suffixes is None else suffixes
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        paths = diffscope.git_paths(["ls-files", "--", *globs])
        if paths is None:
            return Report([], 0, 0, True)
        for rel in paths:
            if not diffscope.ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, True)
        base = diffscope.run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, True)
        diff = diffscope.run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                                  base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, True)
        added, deleted = diffscope.parse_diff(diff)
        for rel, numbered in added.items():
            if diffscope.ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if not (text.strip() and text in deleted)}

    findings: List[Tuple[str, Finding]] = []
    files = lines = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        for finding in scan_file(rel, content, suffixes)[0]:
            if keep is None or finding.line in keep:
                findings.append((rel, finding))
    return Report(findings, files, lines, False)


def main() -> int:
    base_ref = os.environ.get("CLN_BASE_REF", "").strip()
    globs = os.environ.get("CLN_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    suffixes = (split_words(os.environ.get("CLN_SUFFIXES", DEFAULT_SUFFIXES))
                or DEFAULT_SUFFIXES.split())
    ignores = diffscope.compile_ignores(
        diffscope.split_list(os.environ.get("CLN_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("CLN_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("CLN_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree, suffixes)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        # With no base-ref (a push run) the skip is expected, so it is not an annotation.
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the language-suffix name check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every suffixed name the repository already has)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s) "
        f"for names ending in {' '.join(suffixes)} (scope: {scope})."
    )
    if not report.findings:
        print("No language-suffixed names assigned.")
        return 0

    severity = "error" if fail else "warning"
    for rel, finding in report.findings:
        print(f"::{severity} file={rel},line={finding.line}::"
              f"{format_message(finding)}")
    print(f"\n{len(report.findings)} language-suffixed name(s) assigned.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
