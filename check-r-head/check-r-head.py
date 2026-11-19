#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag ``head()`` that a pull request adds to print a dataset in a data div.

The lab's rule (Ezra, 2026-11-19, gha#2122): "stop adding head() in r", then
"head is ok for other purposes, just not printing", and finally "just not to
print data in data divs".  On Morrison-Lab/lds#2862 he wrote "don't use head
in r; use paged or tibble for df-print instead".  So where a page shows a
dataset, its R chunk prints the data frame itself, and the format's
``df-print`` decides how much each reader sees: ``paged`` on the website and
in the slide decks, ``tibble`` in the PDF handouts.

Where the rule applies, in ``.qmd``, ``.Rmd`` and ``.md`` files:

- every ``{r}`` chunk of a data subfile, a file whose name matches
  ``CRH_DATA_FILES`` (default ``_dat-*``, which covers lds's
  ``_dat-<name>.qmd`` divs and ``_dat-<name>-preview.qmd`` previews);
- every ``{r}`` chunk inside a fenced div whose id starts ``#dat-``.

What is flagged there: an R statement whose value prints and comes from
``head()``:

- a bare call, ``head(df)`` or ``utils::head(df, 3)``;
- a pipeline whose last stage is ``head``: ``df |> head()``,
  ``df %>% head(n = 3)``, ``df %>% head``;
- the same wrapped in ``print()``: ``print(head(df))``,
  ``df |> head() |> print()``.

What is not flagged:

- anything outside a data subfile or a ``#dat-`` div;
- an assignment, ``top <- head(df)`` or ``df |> head() -> top``;
- ``head()`` passed to another call, ``nrow(head(df))``, or followed by
  another pipeline stage, ``df |> head() |> knitr::kable()``;
- a statement inside braces (a function body, a loop), whose value does not
  print at top level;
- a method or field such as ``df.head()``, ``x$head()`` or ``slice_head()``;
- ``head`` inside an R comment or a string;
- any chunk whose engine is not R (``{python}``, ``{julia}``, a plain ``r``
  fence, an escaped ``{{r}}`` chunk shown as text), including a chunk shown
  inside a longer fence;
- a statement carrying, or following, ``# check-r-head: allow: <reason>``.
  The reason is required: a bare ``allow`` exempts nothing.

Design notes, in the model of ``check-iterate-subscripts``:

- **Diff-scoped by default.** A statement is reported when a PR adds any of
  its lines, so existing pages never block.  An added line whose exact text
  was also deleted in the same diff is treated as moved.
  ``CRH_WHOLE_TREE=true`` scans everything.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning instead of scanning the whole tree.
- **Blocks by default** (``CRH_FAIL`` defaults to true).
- **The search space is reported.** Every run prints how many files and lines
  it examined.

Configuration (environment variables, set by the composite action):
  CRH_BASE_REF     Git ref/SHA to diff against. Empty and not whole-tree =>
                   skip the check.
  CRH_GLOBS        Space-separated git pathspecs.
  CRH_DATA_FILES   Space- or comma-separated file-name patterns (``*``, ``?``)
                   of data subfiles, matched against the base name.
  CRH_PATHS_IGNORE Comma/newline-separated glob patterns to skip (``*``,
                   ``?`` and recursive ``**``).
  CRH_FAIL         "false" => warn only.
  CRH_WHOLE_TREE   "true" => scan every tracked matching file in full.
"""

import fnmatch
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
DEFAULT_DATA_FILES = "_dat-*"
_DEFAULT_FAIL = True

BACKSLASH = chr(92)

# An executable R chunk's info string: ``{r}``, ``{r label}``,
# ``{r, echo=FALSE}``, ``{R}``.  ``{{r}}`` (shown as text) and ``{rcpp}``
# are not R chunks.
R_CHUNK_RE = re.compile(r"^\{\s*[rR](?![\w.])")

# A fenced div opener (``::: {#dat-auto .x}``) and a bare closer (``:::``).
DIV_OPEN_RE = re.compile(r"^\s*:{3,}\s*\{([^}]*)\}")
DIV_CLOSE_RE = re.compile(r"^\s*:{3,}\s*$")
DAT_ID_RE = re.compile(r"(?:^|\s)#dat-")

# The allow comment needs a reason after ``allow:``.
ALLOW_RE = re.compile(r"#.*\bcheck-r-head:\s*allow:\s*\S")

# A pipe operator: native ``|>`` or magrittr ``%>%``.  Other ``%...%``
# operators (``%in%``, ``%%``) are not pipes.
PIPE_RE = re.compile(r"\|>|%>%")

# A line ending in one of these continues the statement on the next line.
CONTINUES_RE = re.compile(
    r"(?:\|>|%[^%\s]*%|<<?-|->>?|[-+*/^,=&|~<>!:(\[{])\s*$")

# A top-level assignment operator; ``=`` but not ``==``, ``<=``, ``>=``, ``!=``.
ASSIGN_RE = re.compile(r"<<-|<-|->>|->|(?<![=<>!])=(?!=)")

# The callee names that cap a print.
HEAD_NAMES = ("head", "utils::head")

OPENERS = "([{"
CLOSERS = ")]}"


class Finding(NamedTuple):
    line: int
    lines: Tuple[int, ...]


def strip_r_line(line: str) -> str:
    """``line`` with the contents of its strings blanked and its comment cut.

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


def depth_change(code: str) -> int:
    """Net bracket depth a stripped line opens."""
    return sum(ch in OPENERS for ch in code) - sum(ch in CLOSERS for ch in code)


def split_top(code: str, pattern: "re.Pattern[str]") -> List[str]:
    """``code`` split at matches of ``pattern`` that sit at bracket depth 0."""
    parts: List[str] = []
    depth = 0
    start = 0
    i = 0
    while i < len(code):
        ch = code[i]
        if ch in OPENERS:
            depth += 1
        elif ch in CLOSERS:
            depth -= 1
        elif depth == 0:
            m = pattern.match(code, i)
            if m and m.end() > i:
                parts.append(code[start:i])
                start = i = m.end()
                continue
        i += 1
    parts.append(code[start:])
    return parts


def is_assignment(code: str) -> bool:
    """Whether ``code`` assigns at bracket depth 0."""
    return len(split_top(code, ASSIGN_RE)) > 1


def call_parts(stage: str) -> Optional[Tuple[str, str]]:
    """``(callee, arguments)`` when ``stage`` is one call, or a bare name.

    ``head(df, 3)`` gives ``("head", "df, 3")``; a bare ``head`` gives
    ``("head", "")``; anything else (``head(df)[1]``, ``f(x) + 1``) gives None.
    """
    stage = stage.strip()
    m = re.fullmatch(r"([A-Za-z.][\w.]*(?:::[A-Za-z.][\w.]*)?)\s*(.*)", stage,
                     re.DOTALL)
    if not m:
        return None
    callee, rest = m.group(1), m.group(2)
    if not rest:
        return callee, ""
    if not rest.startswith("("):
        return None
    depth = 0
    for i, ch in enumerate(rest):
        if ch in OPENERS:
            depth += 1
        elif ch in CLOSERS:
            depth -= 1
            if depth == 0:
                return (callee, rest[1:i]) if not rest[i + 1:].strip() else None
    return None


def is_head(stage: str) -> bool:
    """Whether ``stage`` is a call to ``head`` (or a bare piped ``head``)."""
    parts = call_parts(stage)
    return parts is not None and parts[0] in HEAD_NAMES


def first_argument(args: str) -> str:
    """The first argument of an argument list."""
    return split_top(args, re.compile(","))[0]


def prints_head(code: str) -> bool:
    """Whether a top-level R statement prints the value of ``head()``."""
    if not code.strip() or is_assignment(code):
        return False
    stages = split_top(code, PIPE_RE)
    last = stages[-1]
    if is_head(last):
        # A bare ``head`` with no pipe before it prints the function itself.
        return len(stages) > 1 or bool(call_parts(last)[1].strip())
    parts = call_parts(last)
    if parts is None or parts[0] != "print":
        return False
    if parts[1].strip():
        return len(stages) == 1 and is_head(first_argument(parts[1]))
    return len(stages) > 1 and is_head(stages[-2])


class Statement(NamedTuple):
    code: str
    lines: Tuple[int, ...]
    allowed: bool


def statements(chunk: List[Tuple[int, str]]) -> List[Statement]:
    """Top-level statements of an R chunk, from ``(line number, text)`` pairs.

    A statement runs on while a bracket is open or a line ends in an operator.
    Statements separated by ``;`` at bracket depth 0 are split.  Braces count
    as brackets, so what sits inside them is never read as top level.
    """
    out: List[Statement] = []
    code: List[str] = []
    numbers: List[int] = []
    allowed = False
    depth = 0
    previous_allows = False
    for number, raw in chunk:
        line_allows = bool(ALLOW_RE.search(raw))
        stripped = strip_r_line(raw)
        if not stripped.strip() and depth == 0 and not code:
            previous_allows = line_allows
            continue
        if not code:
            allowed = previous_allows
        allowed = allowed or line_allows
        code.append(stripped)
        numbers.append(number)
        depth += depth_change(stripped)
        previous_allows = line_allows
        if depth > 0 or CONTINUES_RE.search(stripped):
            continue
        for piece in split_top(" ".join(code), re.compile(";")):
            out.append(Statement(piece, tuple(numbers), allowed))
        code, numbers, depth, allowed = [], [], 0, False
    if code:
        out.append(Statement(" ".join(code), tuple(numbers), allowed))
    return out


def head_line(stmt: Statement, lines: List[str]) -> int:
    """The statement line that names ``head``, else its first line."""
    for number in stmt.lines:
        if re.search(r"\bhead\b", strip_r_line(lines[number - 1])):
            return number
    return stmt.lines[0]


def is_data_file(rel: str, patterns: List[str]) -> bool:
    """Whether the base name of ``rel`` matches a data-subfile pattern."""
    name = rel.replace(BACKSLASH, "/").rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(name, p) for p in patterns)


def scan_file(lines: List[str], data_file: bool = False
              ) -> Tuple[List[Finding], int]:
    """``([Finding, ...], lines examined)`` for a Markdown-family file.

    Only R chunks in scope are read: every one when ``data_file``, else those
    inside a ``#dat-`` div.
    """
    found: List[Finding] = []
    fence: Optional[Tuple[str, int, bool]] = None  # (marker, length, read it)
    chunk: List[Tuple[int, str]] = []
    in_comment = False
    divs: List[bool] = []  # one entry per open div: is it a #dat- div

    def flush() -> None:
        for stmt in statements(chunk):
            if not stmt.allowed and prints_head(stmt.code):
                found.append(Finding(head_line(stmt, lines), stmt.lines))
        chunk.clear()

    for number, raw in enumerate(lines, 1):
        m = mdmask.FENCE_RE.match(raw)
        if fence is None:
            if m and not in_comment:
                in_scope = data_file or any(divs)
                read_it = bool(R_CHUNK_RE.match(m.group(2))) and in_scope
                fence = (m.group(1)[0], len(m.group(1)), read_it)
                continue
            if not in_comment:
                opened = DIV_OPEN_RE.match(raw)
                if opened:
                    divs.append(bool(DAT_ID_RE.search(opened.group(1))))
                elif DIV_CLOSE_RE.match(raw) and divs:
                    divs.pop()
            # HTML comments are tracked so a fence or div inside one opens nothing.
            _, in_comment = mdmask.mask_markdown_line(raw, in_comment)
            continue
        if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                and not m.group(2):
            if fence[2]:
                flush()
            fence = None
            continue
        if fence[2]:
            chunk.append((number, raw))
    if fence is not None and fence[2]:
        flush()
    return found, len(lines)


def format_message(finding: Finding) -> str:
    return ("head() caps how much of a dataset this data-div R statement "
            "prints: print the data frame itself, and let the format's "
            "df-print (paged on the website and in decks, tibble in PDF "
            "handouts) decide how many rows show. head() outside data divs, "
            "or with its result assigned or used, is fine.")


# The git, glob and file helpers come from check-common (gha#1856).
compile_globs = diffscope.compile_ignores


def split_words(value: str) -> List[str]:
    """Words of a space- or comma-separated list."""
    return [word for word in re.split(r"[\s,]+", value.strip()) if word]


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
    files: int
    lines: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool, data_files: Optional[List[str]] = None) -> Report:
    """Scan the added lines since ``base_ref``, or every line when whole-tree."""
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

    patterns = DEFAULT_DATA_FILES.split() if data_files is None else data_files
    findings: List[Tuple[str, Finding]] = []
    files = lines = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        for finding in scan_file(content, is_data_file(rel, patterns))[0]:
            if keep is None or keep.intersection(finding.lines):
                findings.append((rel, finding))
    return Report(findings, files, lines, False)


def main() -> int:
    base_ref = os.environ.get("CRH_BASE_REF", "").strip()
    globs = os.environ.get("CRH_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    data_files = (split_words(os.environ.get("CRH_DATA_FILES", DEFAULT_DATA_FILES))
                  or DEFAULT_DATA_FILES.split())
    ignores = compile_globs(diffscope.split_list(os.environ.get("CRH_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("CRH_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("CRH_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree, data_files)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        # With no base-ref (a push run) the skip is expected, so it is not an annotation.
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the R head() check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every printed head() the repository already has)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s) "
        f"for printed head() in data-div R chunks (scope: {scope})."
    )
    if not report.findings:
        print("No printed head() in data-div R chunks.")
        return 0

    severity = "error" if fail else "warning"
    for rel, finding in report.findings:
        print(f"::{severity} file={rel},line={finding.line}::"
              f"{format_message(finding)}")
    print(f"\n{len(report.findings)} printed head() call(s) in data-div R chunks.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
