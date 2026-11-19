#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag math that leaves the precedence of a logical connective implicit.

The lab's rule (Ezra, 2026-11-19, recorded in Morrison-Lab/ai-config
``shared/writing/math-derivation-steps.md``): in math we write, parentheses
make operator precedence explicit, so a set is written
``\set{x : (x \in A) \lor (x \in B)}`` and not
``\set{x : x \in A \lor x \in B}``.

What is flagged, in ``$...$`` and ``$$...$$`` math of ``.qmd``, ``.md`` and
``.Rmd`` files:

- **A relation beside a connective.** A connective (``\land``, ``\lor``,
  ``\wedge``, ``\vee``, ``\implies``, ``\iff``, ``\Rightarrow``,
  ``\Leftrightarrow``, the long arrows, and their Unicode forms)
  one of whose operands holds an unparenthesized relation (``=``, ``<``,
  ``\le``, ``\in``, ``\notin``, ``\subseteq``, ``\equiv``, ``\mid`` and the
  rest). ``x \in A \lor x \in B`` is flagged; ``(x \in A) \lor (x \in B)``
  is not.
- **Two kinds of connective together.** Two different connectives at one
  level, such as ``P \land Q \lor R`` or ``P \lor Q \implies R``, or a
  repeated implication or biconditional (``P \implies Q \implies R``),
  which are not associative. A repeated ``\land`` or ``\lor`` passes.

An operand ends at a separator as well as at a connective: ``,``, ``;``,
``:``, ``\colon``, ``&``, ``\\``, ``\quad``, ``\qquad``, ``\text{...}`` and a
definition sign (``\eqdef``, ``\coloneqq``, ``:=``). So the ``x`` before the
colon of a set builder is not an operand, and a quantifier's domain
(``\forall x \in A, P(x)``) ends at its comma. A group (parentheses,
brackets, braces, ``\{...\}``, a macro argument) is checked on its own, so
the relation inside ``(x \in A)`` belongs to that group and not to the
connective outside it.

What is not flagged:

- the single arrows ``\to``, ``\rightarrow`` and ``\leftrightarrow``, which
  these notes use for functions, limits and paths far more than for
  implication;
- a connective that opens a clause, such as the ``\iff`` of an aligned
  derivation row (``&\iff x \in S``), which joins the row to the one before;
- code fences and code spans, HTML comments, and YAML front matter;
- a line carrying, or following, ``<!-- check-precedence-parens: allow -->``.

Design notes, in the model of ``check-iterate-subscripts``:

- **Diff-scoped by default.** Only lines *added* since ``CPP_BASE_REF`` are
  reported, so existing pages never block. An added line whose exact text was
  also deleted in the same diff is treated as moved.
  ``CPP_WHOLE_TREE=true`` scans everything, to measure a corpus.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning instead of scanning the whole tree.
- **Blocks by default** (``CPP_FAIL`` defaults to true): both rules are
  deterministic over the token lists below, and the allow comment covers a
  line whose author decided otherwise.
- **Each line is read on its own.** A display block's lines are each one
  expression, so a group open at the end of a line closes there.
- **The search space is reported.** Every run prints how many files and lines
  it examined.

Configuration (environment variables, set by the composite action):
  CPP_BASE_REF     Git ref/SHA to diff against. Empty and not whole-tree =>
                   skip the check.
  CPP_GLOBS        Space-separated git pathspecs.
  CPP_PATHS_IGNORE Comma/newline-separated glob patterns to skip (``*``,
                   ``?`` and recursive ``**``).
  CPP_FAIL         "false" => warn only.
  CPP_WHOLE_TREE   "true" => scan every tracked matching file in full.
"""

import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple, Union

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

ALLOW_RE = re.compile(r"<!--\s*check-precedence-parens:\s*allow\s*-->")

# Each connective maps to its kind; two different kinds at one level are
# flagged, and so is a repeated kind that is not associative.
CONNECTIVES: Dict[str, str] = {
    r"\land": "and", r"\wedge": "and", "∧": "and",
    r"\lor": "or", r"\vee": "or", "∨": "or",
    r"\implies": "implies", r"\Rightarrow": "implies",
    r"\Longrightarrow": "implies", "⇒": "implies", "⟹": "implies",
    r"\impliedby": "impliedby", r"\Leftarrow": "impliedby",
    r"\Longleftarrow": "impliedby", "⇐": "impliedby",
    "⟸": "impliedby",
    r"\iff": "iff", r"\Leftrightarrow": "iff",
    r"\Longleftrightarrow": "iff", "⇔": "iff", "⟺": "iff",
}
# The single arrows (\to, \rightarrow, \leftrightarrow) are left out: in these
# notes they name functions, limits, paths in a digraph and bijections far
# more often than implication, which the lab writes as \Rightarrow.
ASSOCIATIVE = {"and", "or"}

RELATIONS = {
    "=", "<", ">", r"\lt", r"\gt", r"\ne", r"\neq", r"\le", r"\leq",
    r"\ge", r"\geq", r"\leqslant", r"\geqslant", r"\in", r"\notin", r"\ni",
    r"\subset", r"\subseteq", r"\subsetneq", r"\supset", r"\supseteq",
    r"\supsetneq", r"\equiv", r"\not\equiv", r"\cong", r"\approx",
    r"\sim", r"\mid", r"\nmid", r"\divides", r"\ndivides", r"\prec",
    r"\preceq", r"\succ", r"\succeq",
    "≠", "≤", "≥", "∈", "∉", "∋", "⊂",
    "⊆", "⊊", "⊃", "⊇", "≡", "∣", "∤",
}

SEPARATORS = {
    ",", ";", ":", r"\colon", "&", "\\\\", r"\quad", r"\qquad", r"\eqdef",
    r"\coloneqq", r"\defeq", r"\triangleq", ":=", r"\text", r"\textrm",
    r"\textit", r"\textbf", r"\mbox", r"\mathrm", r"\operatorname",
    r"\forall", r"\exists", "∀", "∃",
}

OPENERS = {"(", "[", "{", r"\{", r"\lbrace", r"\langle", "⟨"}
PAIRS = {"(": ")", "[": "]", "{": "}", r"\{": r"\}", r"\lbrace": r"\rbrace",
         r"\langle": r"\rangle", "⟨": "⟩"}
CLOSERS = set(PAIRS.values())
# Sizing prefixes carry no meaning of their own; the delimiter after them does.
SIZERS = {r"\left", r"\right", r"\bigl", r"\bigr", r"\Bigl", r"\Bigr",
          r"\biggl", r"\biggr", r"\Biggl", r"\Biggr", r"\big", r"\Big",
          r"\bigg", r"\Bigg", r"\middle"}

TOKEN_RE = re.compile(r":=|\\not\s*\\[A-Za-z]+|\\[A-Za-z]+|\\.|\S")

Item = Union[str, "Group"]


class Group(NamedTuple):
    items: List[Item]
    opener: str = "("


class Finding(NamedTuple):
    line: int
    rule: str      # "relation" or "mixed"
    detail: str    # the operand, or the connectives


def tokenize(math: str) -> List[str]:
    """TeX-ish tokens of ``math``: control words, escapes, single characters."""
    tokens = []
    for tok in TOKEN_RE.findall(math):
        if tok.startswith(r"\not"):
            tok = r"\not" + tok[4:].strip()
        if tok not in SIZERS:
            tokens.append(tok)
    return tokens


def parse(tokens: List[str]) -> Group:
    """A tree of groups; a stray closer is dropped and an open group ends."""
    root = Group([])
    stack = [root]
    for tok in tokens:
        if tok in OPENERS:
            group = Group([], tok)
            stack[-1].items.append(group)
            stack.append(group)
        elif tok in CLOSERS:
            if len(stack) > 1:
                stack.pop()
        else:
            stack[-1].items.append(tok)
    return root


def _render(items: List[Item]) -> str:
    out = []
    for item in items:
        if isinstance(item, Group):
            close = PAIRS.get(item.opener, ")")
            out.append(f"{item.opener}{_render(item.items)}{close}")
        else:
            out.append(item)
    return " ".join(out)


def _split(items: List[Item], at) -> List[Tuple[Optional[str], List[Item]]]:
    """``items`` cut at each token ``at`` accepts, with the token before each part."""
    parts: List[Tuple[Optional[str], List[Item]]] = [(None, [])]
    for item in items:
        if isinstance(item, str) and at(item):
            parts.append((item, []))
        else:
            parts[-1][1].append(item)
    return parts


def check_group(group: Group) -> List[Tuple[str, str]]:
    """``(rule, detail)`` for this group and every group inside it."""
    found: List[Tuple[str, str]] = []
    for item in group.items:
        if isinstance(item, Group):
            found.extend(check_group(item))
    for _, clause in _split(group.items, lambda t: t in SEPARATORS):
        parts = _split(clause, lambda t: t in CONNECTIVES)
        if len(parts) < 2:
            continue
        # A connective that opens the clause (``&\iff ...`` in an aligned
        # derivation) joins the whole row to the row before, so it is not one
        # of this clause's connectives.
        if not parts[0][1]:
            parts = parts[1:]
            if len(parts) < 2:
                continue
        joined = [conn for conn, _ in parts[1:]]
        kinds = [CONNECTIVES[c] for c in joined]
        if len(set(kinds)) > 1 or any(k not in ASSOCIATIVE for k in kinds[1:]
                                      if kinds.count(k) > 1):
            found.append(("mixed", " ".join(joined)))
        for _, operand in parts:
            if any(isinstance(t, str) and t in RELATIONS for t in operand):
                found.append(("relation", _render(operand)))
    return found


def check_math(math: str) -> List[Tuple[str, str]]:
    """``(rule, detail)`` for each precedence left implicit in ``math``."""
    return check_group(parse(tokenize(math)))


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
            found.extend(Finding(number, rule, detail)
                         for rule, detail in check_math(masked[start:end]))
    return found, examined


def format_message(finding: Finding) -> str:
    if finding.rule == "relation":
        return (f"Parenthesize the relation '{finding.detail}' beside a logical "
                f"connective, as in (x \\in A) \\lor (x \\in B), so the "
                f"precedence is explicit.")
    return (f"Parenthesize to show how '{finding.detail}' group, as in "
            f"(P \\land Q) \\lor R, so the precedence is explicit.")


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
    base_ref = os.environ.get("CPP_BASE_REF", "").strip()
    globs = os.environ.get("CPP_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_globs(diffscope.split_list(os.environ.get("CPP_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("CPP_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("CPP_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        # With no base-ref (a push run) the skip is expected, so it is not an annotation.
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the precedence-parentheses check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every implicit precedence the repository already has)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s) "
        f"for logical connectives with implicit precedence (scope: {scope})."
    )
    if not report.findings:
        print("No implicit precedence.")
        return 0

    severity = "error" if fail else "warning"
    for rel, finding in report.findings:
        print(f"::{severity} file={rel},line={finding.line}::"
              f"{format_message(finding)}")
    print(f"\n{len(report.findings)} implicit precedence(s).")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
