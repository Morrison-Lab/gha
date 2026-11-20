#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a neighborhood written as a norm inequality, such as ``\norm{\vx - \vx^*} < \delta``.

The lab's rule (psw ``chapters/notation/balls-not-inequalities.qmd``):
write that a point lies near another as membership in a ball,
``\vx \in \ball{\vx^*}{\delta}``, rather than as an inequality on the distance
between them. Ezra asked for the rule on 2026-11-20, after rewriting the local
maximizer definition in mds.

What is flagged, in math on lines a PR adds to ``.qmd``, ``.md`` and ``.Rmd``
files: a norm or absolute value of a difference, followed by ``<``, ``\lt``,
``\le``, ``\leq`` or ``\leqslant`` and a right-hand side that holds no other
norm or absolute value. The norm may be written ``\norm{...}``, ``\abs{...}``,
``\|...\|``, ``|...|``, ``\lVert...\rVert`` or ``\lvert...\rvert``, with or
without ``\left``, ``\right`` and sizing commands, and may carry a subscript
(``\norm{\vx - \vy}_2``). The message suggests ``\vx \in \ball{\vy}{r}``
(``<``) or a closed ball (``\le``).

What is not flagged:

- a norm with no difference inside, such as ``\norm{\vw} \le t``, because the
  constrained form of a penalized fit is usually written that way on purpose;
- a comparison of two distances, such as the triangle inequality
  ``\norm{\vx - \vz} \le \norm{\vx - \vy} + \norm{\vy - \vz}`` or a Lipschitz
  bound ``\abs{f(x) - f(y)} \le L \abs{x - y}``, because the right-hand side
  holds a norm or absolute value: neither statement is a neighborhood;
- a ``>`` or ``\ge`` condition (the complement of a ball);
- code fences and code spans, HTML comments, and YAML front matter;
- a line carrying, or following,
  ``<!-- check-ball-neighborhoods: allow: <reason> -->``.

Design notes, in the model of ``check-iterate-subscripts``:

- **Diff-scoped by default.** Only lines *added* since ``CBN_BASE_REF`` are
  reported, so existing pages never block. An added line whose exact text was
  also deleted in the same diff is treated as moved.
  ``CBN_WHOLE_TREE=true`` scans everything.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning instead of scanning the whole tree.
- **Blocks by default** (``CBN_FAIL`` defaults to true). Measured
  2026-11-20 over lds, mds, pds, sds, mcs and psw (whole tree): 49 hits,
  45 of them neighborhoods. Two of the other four are the ball's own
  definition, which takes the allow comment. A step-size condition such as
  ``\abs{1 - \steplen} < 1`` is skipped (a number as the first operand).
- **The search space is reported.** Every run prints how many files and lines
  it examined.

Configuration (environment variables, set by the composite action):
  CBN_BASE_REF     Git ref/SHA to diff against. Empty and not whole-tree =>
                   skip the check.
  CBN_GLOBS        Space-separated git pathspecs.
  CBN_PATHS_IGNORE Comma/newline-separated glob patterns to skip (``*``,
                   ``?`` and recursive ``**``).
  CBN_FAIL         "false" => warn only.
  CBN_WHOLE_TREE   "true" => scan every tracked matching file in full.
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
_DEFAULT_FAIL = True

ALLOW_RE = re.compile(r"<!--\s*check-ball-neighborhoods:\s*allow:\s*\S.*?-->")

# A relation that bounds a distance from above: ``<``, ``\lt``, ``\le``,
# ``\leq``, ``\leqslant``. ``<`` must not be part of ``<-`` or ``<=``-like
# ASCII arrows, which do not appear in TeX math anyway.
RELATION_RE = re.compile(r"<(?![<=-])|\\(?:lt|leqslant|leq|le)(?![A-Za-z])")
CLOSED = {"\\le", "\\leq", "\\leqslant"}

# Sizing commands that may sit before a closing delimiter.
SIZING_RE = re.compile(r"\\(?:right|bigr|Bigr|biggr|Biggr|big|Big|bigg|Bigg)\s*$")

# What ends the right-hand side of the relation.
RHS_END_RE = re.compile(
    r"(?<!\\)[,;&]|\\\\|\\(?:text|textrm|quad|qquad|implies|Rightarrow|Longrightarrow|"
    r"iff|Leftrightarrow|land|lor|wedge|vee|mid|colon|forall|exists|"
    r"text[a-z]*)(?![A-Za-z])"
)
# A norm or absolute value on the right-hand side means the statement compares
# two distances (triangle inequality, Lipschitz bound), not a neighborhood.
RHS_NORM_RE = re.compile(r"\\norm|\\abs|\\\||\||\\[lr][Vv]ert(?![A-Za-z])")

NORM_MACROS = ("norm", "abs")


class Finding(NamedTuple):
    line: int
    text: str
    closed: bool


def _skip_left_ws(text: str, end: int) -> int:
    while end > 0 and text[end - 1].isspace():
        end -= 1
    return end


def _strip_subscript(text: str, end: int) -> int:
    r"""Index before a trailing ``_x``, ``_{...}`` or ``_\name`` ending at ``end``."""
    end = _skip_left_ws(text, end)
    if end > 0 and text[end - 1] == "}":
        start = _match_open_brace(text, end - 1)
        if start is not None:
            before = _skip_left_ws(text, start)
            if before > 0 and text[before - 1] == "_":
                return _skip_left_ws(text, before - 1)
        return end
    m = re.search(r"_\s*(?:\\[A-Za-z]+|[A-Za-z0-9])$", text[:end])
    if m:
        return _skip_left_ws(text, m.start())
    return end


def _match_open_brace(text: str, close: int) -> Optional[int]:
    """Index of the ``{`` matching the ``}`` at ``close``, or None."""
    depth = 0
    i = close
    while i >= 0:
        ch = text[i]
        escaped = i > 0 and text[i - 1] == "\\"
        if ch == "}" and not escaped:
            depth += 1
        elif ch == "{" and not escaped:
            depth -= 1
            if depth == 0:
                return i
        i -= 1
    return None


def _depth_zero(text: str) -> List[bool]:
    """Per character of ``text``, whether it sits outside every group."""
    flags: List[bool] = []
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            # A control symbol such as \{ or \| is one token at this depth.
            flags.extend([depth == 0, depth == 0])
            i += 2
            continue
        if ch in "{([":
            flags.append(depth == 0)
            depth += 1
        elif ch in "})]":
            depth = max(depth - 1, 0)
            flags.append(depth == 0)
        else:
            flags.append(depth == 0)
        i += 1
    return flags


NUMBER_FIRST_RE = re.compile(r"\s*\d+(?:\.\d+)?\s*-")


def has_difference(content: str) -> bool:
    r"""Whether ``content`` holds a binary minus outside every group.

    A difference whose first operand is a number, such as ``1 - \steplen``
    in a step-size condition ``\abs{1 - \steplen} < 1``, bounds a factor
    rather than describing a neighborhood of a point, so it does not count.
    """
    if NUMBER_FIRST_RE.match(content):
        return False
    body = content.strip()
    flags = _depth_zero(body)
    seen_operand = False
    for i, ch in enumerate(body):
        if ch.isspace():
            continue
        if ch == "-" and flags[i] and seen_operand and not (
                i > 0 and body[i - 1] == "\\"):
            return True
        seen_operand = True
    return False


def _previous_delim(text: str, end: int, token: str) -> Optional[int]:
    """Start of the previous ``token`` before ``end`` at the same group depth."""
    depth = 0
    i = end - 1
    while i >= 0:
        ch = text[i]
        escaped = i > 0 and text[i - 1] == "\\"
        if ch in "})]" and not escaped:
            depth += 1
        elif ch in "{([" and not escaped:
            if depth == 0:
                return None
            depth -= 1
        elif depth == 0 and text.startswith(token, i):
            if token == "|" and escaped:
                i -= 1
                continue
            if token == "|" and i + 1 < len(text) and text[i + 1] == "|":
                i -= 1
                continue
            return i
        i -= 1
    return None


def norm_before(math: str, rel_start: int) -> Optional[Tuple[int, str]]:
    """``(start, content)`` of a norm or absolute value ending just before ``rel_start``."""
    end = _strip_subscript(math, rel_start)
    if end == 0:
        return None
    if math[end - 1] == "}":
        open_at = _match_open_brace(math, end - 1)
        if open_at is None:
            return None
        head = math[:open_at].rstrip()
        m = re.search(r"\\(" + "|".join(NORM_MACROS) + r")\*?$", head)
        if not m:
            return None
        return m.start(), math[open_at + 1:end - 1]
    for close, open_ in (("\\rVert", "\\lVert"), ("\\rvert", "\\lvert"),
                         ("\\|", "\\|"), ("|", "|")):
        if not math[:end].endswith(close):
            continue
        if close == "|" and math[:end].endswith("\\|"):
            continue
        inner_end = end - len(close)
        stripped = SIZING_RE.search(math[:inner_end])
        if stripped:
            inner_end = stripped.start()
        start = _previous_delim(math, inner_end, open_)
        if start is None:
            return None
        content_start = start + len(open_)
        # Drop \left or a sizing command before the opening delimiter.
        lead = re.search(r"\\(?:left|bigl|Bigl|biggl|Biggl|big|Big|bigg|Bigg)\s*$",
                         math[:start])
        return (lead.start() if lead else start), math[content_start:inner_end]
    return None


def rhs_of(math: str, after: int) -> str:
    """The right-hand side of the relation, up to its first separator."""
    rest = math[after:]
    flags = _depth_zero(rest)
    m = None
    for found in RHS_END_RE.finditer(rest):
        if flags[found.start()]:
            m = found
            break
    end = m.start() if m else len(rest)
    # A closing bracket of an enclosing group also ends it.
    depth = 0
    for i, ch in enumerate(rest[:end]):
        escaped = i > 0 and rest[i - 1] == "\\"
        if ch in "{([" and not escaped:
            depth += 1
        elif ch in "})]" and not escaped:
            if depth == 0:
                end = i
                break
            depth -= 1
    return rest[:end]


def ball_conditions(math: str) -> List[Tuple[str, bool]]:
    """``(condition text, closed)`` for each norm-inequality neighborhood in ``math``."""
    found: List[Tuple[str, bool]] = []
    for rel in RELATION_RE.finditer(math):
        hit = norm_before(math, rel.start())
        if hit is None:
            continue
        start, content = hit
        if not has_difference(content):
            continue
        rhs = rhs_of(math, rel.end())
        if not rhs.strip() or RHS_NORM_RE.search(rhs):
            continue
        text = " ".join(math[start:rel.end() + len(rhs)].split())
        found.append((text, rel.group(0) in CLOSED))
    return found


def scan_file(lines: List[str]) -> Tuple[List[Finding], int]:
    """``([Finding, ...], lines examined)`` for a Markdown-family file."""
    found: List[Finding] = []
    examined = 0
    fence: Optional[Tuple[str, int]] = None  # (marker, length)
    in_comment = False
    in_display = False
    in_front = bool(lines) and lines[0].strip() == "---"
    for number, raw in enumerate(lines, 1):
        examined += 1
        if in_front:
            if number > 1 and raw.strip() in ("---", "..."):
                in_front = False
            continue
        m = mdmask.FENCE_RE.match(raw)
        if fence is None and m and not in_comment:
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                    and not m.group(2):
                fence = None
            continue
        masked, in_comment = mdmask.mask_markdown_line(raw, in_comment)
        spans, in_display = mdmask.math_spans(masked, in_display)
        allowed = ALLOW_RE.search(raw) or (
            number > 1 and ALLOW_RE.search(lines[number - 2]))
        if allowed:
            continue
        for start, end in spans:
            found.extend(Finding(number, text, closed)
                         for text, closed in ball_conditions(masked[start:end]))
    return found, examined


def format_message(finding: Finding) -> str:
    kind = ("a closed ball of radius r around \\vy" if finding.closed
            else "a ball, as in \\vx \\in \\ball{\\vy}{r}")
    return (f"'{finding.text}' states a neighborhood as a distance inequality; "
            f"write it as membership in {kind} (psw notation rule: balls, "
            f"not inequalities). If this is not a neighborhood, add "
            f"<!-- check-ball-neighborhoods: allow: <reason> -->.")


# The git, glob and file helpers come from check-common (gha#1856).
compile_globs = diffscope.compile_ignores


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
    files: int
    lines: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
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

    findings: List[Tuple[str, Finding]] = []
    files = lines = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        for finding in scan_file(content)[0]:
            if keep is None or finding.line in keep:
                findings.append((rel, finding))
    return Report(findings, files, lines, False)


def main() -> int:
    base_ref = os.environ.get("CBN_BASE_REF", "").strip()
    globs = os.environ.get("CBN_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_globs(diffscope.split_list(os.environ.get("CBN_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("CBN_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("CBN_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        # With no base-ref (a push run) the skip is expected, so it is not an annotation.
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the ball-neighborhood check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every norm inequality the repository already has)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s) "
        f"for neighborhoods written as norm inequalities (scope: {scope})."
    )
    if not report.findings:
        print("No neighborhoods written as norm inequalities.")
        return 0

    severity = "error" if fail else "warning"
    for rel, finding in report.findings:
        print(f"::{severity} file={rel},line={finding.line}::"
              f"{format_message(finding)}")
    print(f"\n{len(report.findings)} neighborhood(s) written as norm inequalities.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
