#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a tree written only as a nested list.

The lab's rule (Ezra, 2026-10-26; Morrison-Lab/gha#1263): a tree (a parse
tree, decision tree, dendrogram or any other hierarchy) is drawn as a diagram
figure, not only written as nested bullets. A reader finds a node's parent
faster in a diagram than by counting indentation.

A div is flagged when all of these hold:

- it is a definition, example, theorem-type, remark or exercise div
  (``#def-``, ``#exm-``, ``#thm-``, ``#lem-``, ``#cor-``, ``#prp-``,
  ``#rem-``, ``#exr-``);
- its text mentions a tree (the word "tree" or "trees", or "dendrogram");
- it holds a list nested to three or more levels (three distinct
  indentation widths among its list items);
- it holds no figure: a Markdown image, an ``<img`` tag, a ``{#fig-`` div, a
  ``fig-`` labelled chunk, an ``@fig-`` reference or an include of a ``_fig``
  subfile.

Keep the list too when it adds information, and add the figure beside it.
A justified exception carries ``<!-- no-tree-figure: reason -->`` inside the
div, and ``paths-ignore`` exempts whole paths.

Design notes, in the model of ``check-exm-figures``, whose parsing and git
helpers this script imports rather than copies:

- **Diff-scoped by default.** A div is reported only when it holds a line the
  diff adds, so the corpus's existing trees are not reflagged. The whole file
  is parsed, since a div opens far above the line that changed.
  ``TLS_WHOLE_TREE=true`` scans every tracked file, which measures how many
  trees are lists.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning.
- **Blocking by default** (``TLS_FAIL`` defaults to true).

Configuration (environment variables, set by the composite action):
  TLS_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  TLS_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  TLS_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  TLS_FAIL          "false" => warn only; default "true".
  TLS_WHOLE_TREE    "true" => scan every tracked matching file in full.
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
exf = _load_sibling("check-exm-figures")

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = True
MIN_LEVELS = 3

ADVICE = (
    "draw the tree as a diagram figure (keep the list too if it adds "
    "information), or add <!-- no-tree-figure: reason --> inside the div"
)

DIV_ID_RE = re.compile(r"#(?:def|exm|thm|lem|cor|prp|rem|exr)-")
TREE_RE = re.compile(r"\b(?:trees?|dendrograms?)\b", re.IGNORECASE)
ITEM_RE = re.compile(r"^( *)(?:[-*+]|\d+[.)])\s+\S")
EXEMPT_RE = re.compile(r"<!--\s*no-tree-figure:\s*(?!-->)\S")


class Div(NamedTuple):
    start: int  # 1-based line of the opening fence
    end: int    # 1-based line of the closing fence
    attrs: str


def scan_divs(lines: List[str]) -> List[Div]:
    """Every labelled div outside code fences and HTML comments."""
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    stack: List[Tuple[int, str]] = []
    found: List[Div] = []
    for idx, raw in enumerate(lines):
        if fence is None:
            raw, in_comment = ods.strip_comments(raw, in_comment)
        m = ods.FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        dm = ods.DIV_RE.match(raw)
        if not dm:
            continue
        if dm.group(2):
            stack.append((idx + 1, dm.group(2)))
        elif stack:
            start, attrs = stack.pop()
            if DIV_ID_RE.search(attrs):
                found.append(Div(start, idx + 1, attrs))
    return found


def list_levels(body: List[str]) -> int:
    """Distinct indentation widths among the list items outside code fences."""
    widths: Set[int] = set()
    in_code = False
    for line in body:
        if ods.FENCE_RE.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = ITEM_RE.match(line.replace("\t", "    "))
        if m:
            widths.add(len(m.group(1)))
    return len(widths)


def mentions_tree(body: List[str]) -> bool:
    return any(TREE_RE.search(line) for line in body)


def has_figure(body: List[str]) -> bool:
    return exf.has_figure(body)


def is_exempt(body: List[str]) -> bool:
    return any(EXEMPT_RE.search(line) for line in body)


def is_tree_list(body: List[str]) -> bool:
    return (mentions_tree(body) and list_levels(body) >= MIN_LEVELS
            and not has_figure(body) and not is_exempt(body))


def scan_file(lines: List[str], keep: Optional[Set[int]]) -> Tuple[List[Div], int]:
    """Divs holding a tree list with no figure that hold a kept line."""
    flagged: List[Div] = []
    divs = scan_divs(lines)
    for div in divs:
        body = lines[div.start - 1:div.end]
        if not is_tree_list(body):
            continue
        if keep is None or any(div.start <= n <= div.end for n in keep):
            flagged.append(div)
    return flagged, len(divs)


def format_message(attrs: str) -> str:
    ident = re.search(r"#(?:def|exm|thm|lem|cor|prp|rem|exr)-[\w:.-]+", attrs)
    name = ident.group(0) if ident else "div"
    return (f"Div {name} writes a tree as a nested list with no figure. "
            f"Fix: {ADVICE}")


class Report(NamedTuple):
    findings: List[Tuple[str, int, str]]  # (path, opening line, attrs)
    files: int
    lines: int
    divs: int
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

    findings: List[Tuple[str, int, str]] = []
    files = lines = divs = 0
    for rel in sorted(wanted):
        content = ods._read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        flagged, seen = scan_file(content, keep)
        divs += seen
        findings.extend((rel, d.start, d.attrs) for d in flagged)
    return Report(findings, files, lines, divs, False)


def main() -> int:
    base_ref = os.environ.get("TLS_BASE_REF", "").strip()
    globs = os.environ.get("TLS_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = ods.compile_ignores(ods._split_list(os.environ.get("TLS_PATHS_IGNORE", "")))
    fail = ods._env_flag("TLS_FAIL", _DEFAULT_FAIL)
    whole_tree = ods._env_flag("TLS_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the tree-list check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every tree the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s), "
        f"{report.divs} labelled div(s) (scope: {scope})."
    )
    severity = "error" if fail else "warning"
    for rel, line, attrs in report.findings:
        print(f"::{severity} file={rel},line={line}::{format_message(attrs)}")
    if not report.findings:
        print("No examined div writes a tree only as a nested list.")
        return 0
    print(f"\n{len(report.findings)} div(s) write a tree only as a nested list.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
