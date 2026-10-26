#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag an axis title that is only a symbol or an expression.

The lab's rule (Ezra, 2026-10-26; Morrison-Lab/gha#1235): an axis title names
the quantity in plain words, and the symbol is optional. Write "Probability, p"
and "Log-odds, η", not "p", "z", "x1" or "f(x)". A reader should not have to
look up a symbol to know what an axis shows.

What counts as an axis title, in a line a diff adds:

- ggplot2 ``labs(x = "...", y = "...")``, including a call that spans lines,
  and ``xlab("...")`` / ``ylab("...")``;
- matplotlib ``set_xlabel("...")`` / ``set_ylabel("...")`` (and ``set_zlabel``);
- plotly ``xaxis_title="..."`` / ``yaxis_title="..."``, and ``title="..."``
  inside an ``xaxis = list(...)`` / ``yaxis=dict(...)`` on the same line.

A title is flagged when it holds no plain word. After math spans (``$...$``)
are dropped, a word is a run of three or more letters, so "x", "x1", "f(x)",
"y h(x)" and "$\hat{y}$" are flagged, and "mpg", "Log-odds, η" and "Weight (lb)"
are not. ``NULL``, a string with no letter or digit (empty, or a ``"..."``
placeholder), and a title built from a variable or call
(not a quoted literal) are not examined.

A justified exception puts ``axis-title-ok: reason`` anywhere on the line
(for example in a ``# axis-title-ok: ...`` comment). A comment with no reason
does not exempt it. Whole paths are exempt through ``paths-ignore``.

Design notes, in the model of ``check-exm-figures``, whose parsing and git
helpers this script imports rather than copies:

- **Diff-scoped by default.** A title is reported only when its line is one the
  diff adds; an added line whose exact text was also deleted is moved, not new.
  A ``labs()`` call is read across lines, so ``x = "x"`` on a continuation line
  is attributed to the line it is on.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``AXT_WHOLE_TREE=true`` scans every
  tracked file, which measures how many titles the corpus already carries.
- **Blocking by default.**
- **The search space is reported**: files, lines and titles examined.

Configuration (environment variables, set by the composite action):
  AXT_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  AXT_GLOBS         Space-separated git pathspecs
                    (default: '*.qmd *.Rmd *.R *.py').
  AXT_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  AXT_FAIL          "false" => warn only; default "true".
  AXT_WHOLE_TREE    "true" => scan every tracked matching file in full.
"""

import importlib.util
import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _load_sibling(name: str):
    """Import a sibling check's script, whose directory name has hyphens."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, os.pardir, name, name + ".py")
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ods = _load_sibling("check-one-div-per-subfile")

DEFAULT_GLOBS = "*.qmd *.Rmd *.R *.py"
_DEFAULT_FAIL = True

ADVICE = (
    "name the quantity in plain words, with the symbol optional "
    '(for example "Probability, p" rather than "p"), or add '
    "axis-title-ok: reason on the line"
)

STR = r"""[rRfFuU]{0,2}(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')"""
CALL_RES = [
    re.compile(r"\b(?:xlab|ylab)\(\s*" + STR),
    re.compile(r"\bset_[xyz]label\(\s*" + STR),
    re.compile(r"\b[xy]axis_title\s*=\s*" + STR),
    re.compile(r"\b[xy]axis\s*=\s*(?:list|dict)\([^)]*?\btitle\s*=\s*" + STR),
]
LABS_START_RE = re.compile(r"\blabs\(")
LABS_ARG_RE = re.compile(r"(?<![\w.])(?:x|y)\s*=\s*" + STR)
MATH_RE = re.compile(r"\$[^$]*\$")
WORD_RE = re.compile(r"[^\W\d_]{3,}")
EXEMPT_RE = re.compile(r"axis-title-ok:\s*\S")


class Title(NamedTuple):
    line: int  # 1-based line holding the string
    text: str


def has_plain_word(title: str) -> bool:
    return bool(WORD_RE.search(MATH_RE.sub(" ", title)))


def _literal(m: "re.Match[str]") -> str:
    return m.group(1) if m.group(1) is not None else m.group(2)


def scan_titles(lines: List[str]) -> List[Title]:
    """Every quoted axis-title literal, with the line it is on."""
    found: List[Title] = []
    depth = 0  # open parentheses of a labs() call that spans lines
    for idx, raw in enumerate(lines):
        if depth > 0:
            segment = raw
        else:
            start = LABS_START_RE.search(raw)
            segment = raw[start.end():] if start else ""
            if start:
                depth = 1
        if depth > 0:
            quoteless = re.sub(STR, '""', segment)
            for m in LABS_ARG_RE.finditer(segment):
                found.append(Title(idx + 1, _literal(m)))
            depth += quoteless.count("(") - quoteless.count(")")
            depth = max(depth, 0)
        for rx in CALL_RES:
            for m in rx.finditer(raw):
                groups = m.groups()
                text = groups[-2] if groups[-2] is not None else groups[-1]
                found.append(Title(idx + 1, text))
    return found


def scan_file(lines: List[str], keep: Optional[Set[int]]) -> Tuple[List[Title], int]:
    """Titles with no plain word on a kept line, and titles seen."""
    bad: List[Title] = []
    titles = scan_titles(lines)
    for t in titles:
        if keep is not None and t.line not in keep:
            continue
        if not re.search(r"\w", t.text) or has_plain_word(t.text):
            continue
        if EXEMPT_RE.search(lines[t.line - 1]):
            continue
        bad.append(t)
    return bad, len(titles)


def format_message(text: str) -> str:
    return f'Axis title "{text}" has no plain word. Fix: {ADVICE}'


class Report(NamedTuple):
    findings: List[Tuple[str, Title]]
    files: int
    lines: int
    titles: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: list,
              whole_tree: bool) -> Report:
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = ods._run_git(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, 0, 0, True)
        for rel in out.splitlines():
            if rel and not ods._ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, 0, True)
        base = ods._run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, 0, True)
        diff = ods._run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                             base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, 0, True)
        added, deleted = ods.parse_diff(diff)
        for rel, numbered in added.items():
            if ods._ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if text.strip() and text not in deleted}

    findings: List[Tuple[str, Title]] = []
    files = lines = titles = 0
    for rel in sorted(wanted):
        content = ods._read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        bad, seen = scan_file(content, keep)
        titles += seen
        findings.extend((rel, t) for t in bad)
    return Report(findings, files, lines, titles, False)


def main() -> int:
    base_ref = os.environ.get("AXT_BASE_REF", "").strip()
    globs = os.environ.get("AXT_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = ods.compile_ignores(ods._split_list(os.environ.get("AXT_PATHS_IGNORE", "")))
    fail = ods._env_flag("AXT_FAIL", _DEFAULT_FAIL)
    whole_tree = ods._env_flag("AXT_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the axis-title check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every title the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s), "
        f"{report.titles} axis title(s) (scope: {scope})."
    )
    severity = "error" if fail else "warning"
    for rel, t in report.findings:
        print(f"::{severity} file={rel},line={t.line}::{format_message(t.text)}")
    if not report.findings:
        print("Every examined axis title holds a plain word or a stated exemption.")
        return 0
    print(f"\n{len(report.findings)} axis title(s) have no plain word.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
