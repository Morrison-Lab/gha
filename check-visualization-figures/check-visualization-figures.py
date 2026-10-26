#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a div whose title mentions visualization but that has no figure.

The lab's rule (Ezra, 2026-10-26): every div whose
title matches ``visuali[sz]`` (visualize, visualizing, visualization) must
have a corresponding figure. For an exercise (``#exr-``) the figure may be in
the exercise or in its solution.

A div's title is the text of the first heading inside it (``#### Title``) or
its ``title="..."`` attribute. The divs checked carry an exercise, example,
definition, result or remark id (``#exr-``, ``#exm-``, ``#def-``, ``#thm-``,
``#lem-``, ``#prp-``, ``#cor-``, ``#rem-``); a ``#fig-`` or ``#sol-`` div is
the figure or the answer itself and is never the subject.

What counts as a figure is what ``check-exm-figures`` counts: an image, a
``fig-`` labelled chunk or div, an ``@fig-`` reference, or an include of a
``_fig`` subfile. For an exercise, the solution is found in this order:

- a ``#sol-<slug>`` div in the same file, where ``<slug>`` is the exercise's
  id without its ``exr-`` prefix;
- a sibling file with ``_exr-`` replaced by ``_sol-`` in its name
  (``_exr-a-part2.qmd`` pairs with ``_sol-a-part2.qmd``).

A div is exempt when it holds ``<!-- no-figure: reason -->`` with a
non-empty reason. Whole paths are exempt through ``paths-ignore``.

Design notes, as in ``check-exm-figures``, whose figure test and the shared
parsing and git helpers of ``check-one-div-per-subfile`` this script imports:

- **Diff-scoped by default**: a div is reported only when it, or the solution
  that is checked with it, holds a line the diff adds. An added line whose
  exact text was also deleted in the diff is moved, not new.
- **Skip, not fall back** when there is no base to diff against;
  ``VIZ_WHOLE_TREE=true`` scans every tracked file.
- **Blocking by default** (``VIZ_FAIL`` defaults to true).

Configuration (environment variables, set by the composite action):
  VIZ_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  VIZ_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  VIZ_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  VIZ_FAIL          "false" => warn only; default "true".
  VIZ_WHOLE_TREE    "true" => scan every tracked matching file in full.
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

ADVICE = (
    "add a figure to the div (for an exercise, to its solution), or add "
    "<!-- no-figure: reason --> inside the div"
)

SUBJECT_RE = re.compile(r"#((?:exr|exm|def|thm|lem|prp|cor|rem)-[\w:.-]+)")
VIZ_RE = re.compile(r"visuali[sz]", re.IGNORECASE)
HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.*\S)")
TITLE_ATTR_RE = re.compile(r"""\btitle\s*=\s*(?:"([^"]*)"|'([^']*)')""")


class Div(NamedTuple):
    start: int  # 1-based line of the opening fence
    end: int    # 1-based line of the closing fence
    attrs: str


def scan_divs(lines: List[str]) -> List[Div]:
    """Every div outside code fences and HTML comments."""
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
            found.append(Div(start, idx + 1, attrs))
    return found


def title_of(lines: List[str], div: Div) -> str:
    """The div's title attribute, else the text of its first heading."""
    attr = TITLE_ATTR_RE.search(div.attrs)
    if attr:
        return attr.group(1) or attr.group(2) or ""
    for line in lines[div.start:div.end - 1]:
        if not line.strip():
            continue
        heading = HEADING_RE.match(line)
        return heading.group(1) if heading else ""
    return ""


def solution_slug(div_id: str) -> Optional[str]:
    return div_id[len("exr-"):] if div_id.startswith("exr-") else None


def sibling_solution(path: str) -> Optional[List[str]]:
    """Lines of the ``_sol-`` file paired with an ``_exr-`` file, if any."""
    folder, name = os.path.split(path)
    if not name.startswith("_exr-"):
        return None
    return ods._read_lines(os.path.join(folder, "_sol-" + name[len("_exr-"):]))


def check_lines(lines: List[str], path: str, keep: Optional[Set[int]],
                solution: Optional[List[str]] = None) -> Tuple[List[Div], int]:
    """Visualization divs with no figure that hold a kept line, and divs seen.

    ``solution`` is the lines of the paired solution file; it defaults to the
    sibling ``_sol-`` file of ``path``.
    """
    divs = scan_divs(lines)
    if solution is None:
        solution = sibling_solution(path)
    same_file_solutions = {
        m.group(1): d for d in divs
        for m in [re.search(r"#(sol-[\w:.-]+)", d.attrs)] if m
    }
    missing: List[Div] = []
    seen = 0
    for div in divs:
        subject = SUBJECT_RE.search(div.attrs)
        if not subject or not VIZ_RE.search(title_of(lines, div)):
            continue
        seen += 1
        body = lines[div.start - 1:div.end]
        if exf.has_figure(body) or exf.is_exempt(body):
            continue
        slug = solution_slug(subject.group(1))
        if slug is not None:
            sol = same_file_solutions.get("sol-" + slug)
            if sol is not None:
                sol_body = lines[sol.start - 1:sol.end]
                if exf.has_figure(sol_body) or exf.is_exempt(sol_body):
                    continue
            if solution is not None and (
                    exf.has_figure(solution) or exf.is_exempt(solution)):
                continue
        if keep is None or any(div.start <= n <= div.end for n in keep):
            missing.append(div)
    return missing, seen


def format_message(attrs: str) -> str:
    ident = SUBJECT_RE.search(attrs)
    name = "#" + ident.group(1) if ident else "div"
    return f"Div {name} has a visualization title but no figure. Fix: {ADVICE}"


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
        # A changed solution file puts its exercise's divs in scope: the
        # exercise holds no added line, but its figure may have been removed.
        for rel in list(wanted):
            folder, name = os.path.split(rel)
            if name.startswith("_sol-"):
                twin = os.path.join(folder, "_exr-" + name[len("_sol-"):])
                if twin not in wanted and os.path.exists(twin):
                    wanted[twin] = None

    findings: List[Tuple[str, int, str]] = []
    files = lines = divs = 0
    for rel in sorted(wanted):
        content = ods._read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        missing, seen = check_lines(content, rel, keep)
        divs += seen
        findings.extend((rel, div.start, div.attrs) for div in missing)
    return Report(findings, files, lines, divs, False)


def main() -> int:
    base_ref = os.environ.get("VIZ_BASE_REF", "").strip()
    globs = os.environ.get("VIZ_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = ods.compile_ignores(ods._split_list(os.environ.get("VIZ_PATHS_IGNORE", "")))
    fail = ods._env_flag("VIZ_FAIL", _DEFAULT_FAIL)
    whole_tree = ods._env_flag("VIZ_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the visualization-figure check for this run "
            f"({reason}; not falling back to a whole-tree scan)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s), "
        f"{report.divs} visualization div(s) (scope: {scope})."
    )
    severity = "error" if fail else "warning"
    for rel, line, attrs in report.findings:
        print(f"::{severity} file={rel},line={line}::{format_message(attrs)}")
    if not report.findings:
        print("Every examined visualization div has a figure or a stated exemption.")
        return 0
    print(f"\n{len(report.findings)} visualization div(s) have no figure.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
