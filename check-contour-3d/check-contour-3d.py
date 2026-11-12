#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a contour or level-curve plot that has no matching 3D surface plot.

The lab's rule (Ezra, 2026-11-03; Morrison-Lab/gha#1443): every contour plot
of a function of two variables gets a matching 3D surface plot of the same
function, so a reader sees the surface the level curves slice.

A contour call is one of ``geom_contour``, ``geom_contour_filled``,
``stat_contour``, ``add_contour``, ``contour(`` (base R, matplotlib's
``.contour(`` and ``.contourf(``), ``Plot.contour`` or a plotly
``type = "contour"``, inside a code fence.

A file is satisfied when any of these holds:

- it holds a 3D call in a code fence (``add_surface``, ``plot_surface``,
  ``plot_trisurf``, ``persp``, ``persp3d``, ``type = "surface"``);
- it includes a 3D figure subfile (``{{< include ..._3d.qmd >}}`` or
  ``...-3d.qmd``);
- a sibling subfile named ``<stem>-3d.qmd`` sits beside it;
- it holds an HTML comment ``<!-- no-3d: reason -->`` with a non-empty
  reason, for a contour plot that is not of a function of two variables, such
  as a density estimated from data.

Whole paths are exempt through ``paths-ignore``.

Design notes, in the model of ``check-exm-figures``, whose parsing and git
helpers this script imports through ``check-one-div-per-subfile``:

- **File-level.** The test is per file, not per figure, so a file with two
  contour figures and one 3D plot passes. Put each figure in its own
  subfile (the lab's one-figure-per-subfile layout) to get a per-figure test.
- **Diff-scoped by default.** A contour call is reported only when its code
  fence holds a line the diff adds, so existing figures are never reflagged.
  An added line whose exact text was also deleted in the same diff is moved,
  not new, and a blank added line is not content.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``C3D_WHOLE_TREE=true`` scans
  every tracked file, which measures how many contour figures lack a 3D plot.
- **Warn-only by default** (``C3D_FAIL`` defaults to false) while the corpus
  catches up; set it to true to block.
- **The search space is reported**: files, lines and contour figures.

Configuration (environment variables, set by the composite action):
  C3D_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  C3D_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  C3D_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  C3D_FAIL          "true" => fail on a finding; default "false".
  C3D_WHOLE_TREE    "true" => scan every tracked matching file in full.
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

# The git and file helpers come from check-common (gha#1856);
# the div and fence parsing still comes from check-one-div-per-subfile.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = False

ADVICE = (
    "add a 3D surface plot of the same function (a sibling <name>-3d.qmd "
    "subfile, included beside this figure), or add <!-- no-3d: reason --> "
    "to the file"
)

CONTOUR_RES = [re.compile(p) for p in (
    r"\b(?:geom|stat)_contour(?:_filled)?\s*\(",
    r"\badd_contour\s*\(",
    r"(?<![\w.])contour\s*\(",
    r"(?<![\w.])filled\.contour\s*\(",
    r"\.contourf?\s*\(",
    r"\bPlot\.contour\b",
    r"\btype\s*=\s*[\"']contour[\"']",
)]
SURFACE_RES = [re.compile(p) for p in (
    r"\badd_surface\s*\(",
    r"\bplot_surface\s*\(",
    r"\bplot_trisurf\s*\(",
    r"\bpersp3?d?\s*\(",
    r"\btype\s*=\s*[\"']surface[\"']",
)]
INCLUDE_3D_RE = re.compile(r"\{\{<\s*include\s+\S*[-_]3d\.qmd")
EXEMPT_RE = re.compile(r"<!--\s*no-3d:\s*(?!-->)\S")


class Figure(NamedTuple):
    start: int  # 1-based line of the opening code fence
    end: int    # 1-based line of the closing code fence
    first_call: int  # 1-based line of the first contour call


def scan_blocks(lines: List[str]) -> Tuple[List[Figure], bool]:
    """Code fences with a contour call, and whether any fence has a 3D call."""
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    start = 0
    call = 0
    has_surface = False
    figures: List[Figure] = []
    for idx, raw in enumerate(lines):
        if fence is None:
            raw, in_comment = ods.strip_comments(raw, in_comment)
        m = ods.FENCE_RE.match(raw)
        if fence is None:
            if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
                fence = (m.group(1)[0], len(m.group(1)))
                start = idx + 1
                call = 0
            continue
        if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                and not m.group(2).strip()):
            if call:
                figures.append(Figure(start, idx + 1, call))
            fence = None
            continue
        if any(r.search(raw) for r in SURFACE_RES):
            has_surface = True
        if not call and any(r.search(raw) for r in CONTOUR_RES):
            call = idx + 1
    return figures, has_surface


def has_3d_sibling(rel: str) -> bool:
    stem, _ = os.path.splitext(rel)
    return os.path.isfile(stem + "-3d.qmd") or os.path.isfile(stem + "_3d.qmd")


def is_satisfied(lines: List[str], has_surface: bool, rel: Optional[str]) -> bool:
    if has_surface:
        return True
    if any(INCLUDE_3D_RE.search(line) or EXEMPT_RE.search(line) for line in lines):
        return True
    return bool(rel) and has_3d_sibling(rel)


def scan_file(lines: List[str], keep: Optional[Set[int]],
              rel: Optional[str] = None) -> Tuple[List[Figure], int]:
    """Contour figures with no 3D plot that hold a kept line, and figures seen."""
    figures, has_surface = scan_blocks(lines)
    if is_satisfied(lines, has_surface, rel):
        return [], len(figures)
    missing = [f for f in figures
               if keep is None or any(f.start <= n <= f.end for n in keep)]
    return missing, len(figures)


class Report(NamedTuple):
    findings: List[Tuple[str, int]]  # (path, line of the first contour call)
    files: int
    lines: int
    figures: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: list,
              whole_tree: bool) -> Report:
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = diffscope.git_paths(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, 0, 0, True)
        for rel in out:
            if rel and not diffscope.ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, 0, True)
        base = diffscope.run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, 0, True)
        diff = diffscope.run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                             base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, 0, True)
        added, deleted = diffscope.parse_diff(diff)
        for rel, numbered in added.items():
            if diffscope.ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if text.strip() and text not in deleted}

    findings: List[Tuple[str, int]] = []
    files = lines = figures = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        missing, seen = scan_file(content, keep, rel)
        figures += seen
        findings.extend((rel, f.first_call) for f in missing)
    return Report(findings, files, lines, figures, False)


def main() -> int:
    base_ref = os.environ.get("C3D_BASE_REF", "").strip()
    globs = os.environ.get("C3D_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = diffscope.compile_ignores(
        diffscope.split_list(os.environ.get("C3D_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("C3D_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("C3D_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the contour-3D check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every contour figure the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s), "
        f"{report.figures} contour figure(s) (scope: {scope})."
    )
    severity = "error" if fail else "warning"
    for rel, line in report.findings:
        print(f"::{severity} file={rel},line={line}::Contour plot has no 3D "
              f"surface plot. Fix: {ADVICE}")
    if not report.findings:
        print("Every examined contour figure has a 3D plot or a stated exemption.")
        return 0
    print(f"\n{len(report.findings)} contour figure(s) have no 3D plot.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
