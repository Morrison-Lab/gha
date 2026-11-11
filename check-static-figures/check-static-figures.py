#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag an interactive figure that has no noninteractive version in static formats.

Rule (Ezra, 2026-11-10; Morrison-Lab/gha#1822, Morrison-Lab/psw#567): "in
static formats (pdf, docx, pptx, etc), we should still render 3d plots and
other interactive figures, just using noninteractive versions".

- **Placeholder**: a line telling readers to see the HTML (or slide) version
  of a figure, in prose or in a chunk that prints it. Reported per line.
- **HTML-only**: a fence that builds an interactive figure (plotly,
  htmlwidgets, leaflet, rgl) and runs only in HTML output (an un-negated
  `is_html_output()` in `#| eval:`, or a `.content-visible when-format="html"`
  or `.content-hidden unless-format="html"` div), in a file with no static
  version: a fence run outside HTML that draws a plot (`persp`, `ggplot`,
  `plt.`, `plot(`, `save_image`, `webshot`, ...). A chunk that only prints a
  note is not a plot. A widget that runs in every format is not flagged,
  since knitr screenshots it in static output when webshot2 is installed.

`<!-- static-version: reason -->` with a non-empty reason exempts a file.
Like `check-contour-3d`: diff-scoped (moved lines are not new), skips rather
than falling back to a whole-tree scan, warn-only by default.

Configuration (environment variables, set by the composite action):
  CSF_BASE_REF      Git ref/SHA to diff against; empty => skip.
  CSF_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  CSF_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  CSF_FAIL          "true" => fail on a finding; default "false".
  CSF_WHOLE_TREE    "true" => scan every tracked matching file in full.
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

EXEMPT_HINT = "or add <!-- static-version: reason --> to the file"
PLACEHOLDER_ADVICE = ("show a noninteractive version of the figure in static "
                      "formats instead of this note, " + EXEMPT_HINT)
HTML_ONLY_ADVICE = ("run the widget in every format so knitr screenshots it, or "
                    "add a chunk that draws a still plot outside HTML, " + EXEMPT_HINT)

PLACEHOLDER_RE = re.compile(
    r"see\s+the\s+(?:HTML|web(?:site)?|online)(?:\s+or\s+slides?)?\s+version",
    re.IGNORECASE,
)
INTERACTIVE_RES = [re.compile(p) for p in (
    r"\bplot_ly\s*\(", r"\bplotly::", r"\bggplotly\s*\(",
    r"^\s*(?:import|from)\s+plotly\b", r"\bgo\.Figure\s*\(",
    r"\bpx\.[a-z_0-9]+\s*\(", r"\bhtmlwidgets::", r"\bleaflet\s*\(",
    r"\brglwidget\s*\(",
)]
STATIC_RES = [re.compile(p) for p in (
    r"\bplot_surface\s*\(", r"\bplot_trisurf\s*\(", r"\bpersp3?D?\s*\(",
    r"\bscatter3D\s*\(", r"\bggplot\s*\(", r"\bplt\.", r"\bax\.[a-z_0-9]+\s*\(",
    r"(?<![\w.])plot\s*\(", r"(?<![\w.])image\s*\(", r"\bsave_image\s*\(",
    r"\bwrite_image\s*\(", r"\bwebshot2?\b", r"\binclude_graphics\s*\(",
)]
EVAL_RE = re.compile(r"^\s*#\|\s*eval\s*:\s*(.*)$")
HTML_TEST_RE = re.compile(r"is_html_output\s*\(\s*\)")
NEGATED_HTML_RE = re.compile(
    r"isFALSE\s*\(\s*(?:knitr::)?is_html_output|!\s*(?:knitr::)?is_html_output"
)
STATIC_TEST_RE = re.compile(r"is_latex_output\s*\(\s*\)")
FORMAT_ATTR_RE = re.compile(r'(when|unless)-format\s*=\s*"([^"]*)"')
HTML_FORMATS = {"html", "revealjs", "html:js"}
EXEMPT_RE = re.compile(r"<!--\s*static-version:\s*(?!-->)\S")


class Fence(NamedTuple):
    start: int  # 1-based line of the opening code fence
    end: int    # 1-based line of the closing code fence
    first_call: int  # 1-based line of the first interactive call (0 if none)
    where: str  # "html", "static" or "all": the outputs the fence runs in
    plots: bool  # draws a still plot


def _div_scope(attrs: str) -> str:
    """The outputs a div's contents appear in: "html", "static" or "all"."""
    visible = ".content-visible" in attrs
    hidden = ".content-hidden" in attrs
    if not (visible or hidden):
        return "all"
    for kind, value in FORMAT_ATTR_RE.findall(attrs):
        formats = {v.strip() for v in value.split(",")}
        is_html = bool(formats) and formats <= HTML_FORMATS
        shown_only = (visible and kind == "when") or (hidden and kind == "unless")
        hidden_only = (visible and kind == "unless") or (hidden and kind == "when")
        if shown_only:
            return "html" if is_html else "static"
        if hidden_only and is_html:
            return "static"
    return "all"


def _eval_scope(option: str) -> str:
    if NEGATED_HTML_RE.search(option) or STATIC_TEST_RE.search(option):
        return "static"
    if HTML_TEST_RE.search(option):
        return "html"
    return "all"


def scan_blocks(lines: List[str]) -> Tuple[List[Fence], List[int], bool]:
    """Code fences, placeholder lines, and whether the file is exempt."""
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    divs: List[Tuple[int, str]] = []  # (colon count, scope)
    start = call = 0
    eval_scope = "all"
    plots = False
    fences: List[Fence] = []
    placeholders: List[int] = []
    exempt = False
    for idx, raw in enumerate(lines):
        if fence is None and EXEMPT_RE.search(raw):
            exempt = True
        if fence is None:
            raw, in_comment = ods.strip_comments(raw, in_comment)
        if PLACEHOLDER_RE.search(raw):
            placeholders.append(idx + 1)
        m = ods.FENCE_RE.match(raw)
        if fence is None:
            if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
                fence = (m.group(1)[0], len(m.group(1)))
                start = idx + 1
                call = 0
                eval_scope = "all"
                plots = False
                continue
            d = ods.DIV_RE.match(raw)
            if d:
                colons, rest = len(d.group(1)), d.group(2)
                if rest:
                    divs.append((colons, _div_scope(rest)))
                else:
                    while divs and divs[-1][0] > colons:
                        divs.pop()
                    if divs:
                        divs.pop()
            continue
        if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                and not m.group(2).strip()):
            where = eval_scope
            for _, scope in divs:
                if scope != "all":
                    where = scope
            fences.append(Fence(start, idx + 1, call, where, plots))
            fence = None
            continue
        e = EVAL_RE.match(raw)
        if e:
            eval_scope = _eval_scope(e.group(1))
            continue
        if not call and any(r.search(raw) for r in INTERACTIVE_RES):
            call = idx + 1
        if any(r.search(raw) for r in STATIC_RES):
            plots = True
    return fences, placeholders, exempt


class Finding(NamedTuple):
    line: int
    kind: str  # "placeholder" or "html-only"


def scan_file(lines: List[str], keep: Optional[Set[int]]) -> Tuple[List[Finding], int]:
    """Findings that hold a kept line, and the interactive figures seen."""
    fences, placeholders, exempt = scan_blocks(lines)
    interactive = [f for f in fences if f.first_call]
    if exempt:
        return [], len(interactive)
    findings = [Finding(n, "placeholder") for n in placeholders
                if keep is None or n in keep]
    has_static = any(f.where == "static" and f.plots for f in fences)
    if not has_static:
        for f in interactive:
            if f.where != "html":
                continue
            if keep is None or any(f.start <= n <= f.end for n in keep):
                findings.append(Finding(f.first_call, "html-only"))
    findings.sort()
    return findings, len(interactive)


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
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

    findings: List[Tuple[str, Finding]] = []
    files = lines = figures = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        found, seen = scan_file(content, keep)
        figures += seen
        findings.extend((rel, f) for f in found)
    return Report(findings, files, lines, figures, False)


def main() -> int:
    base_ref = os.environ.get("CSF_BASE_REF", "").strip()
    globs = os.environ.get("CSF_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = diffscope.compile_ignores(
        diffscope.split_list(os.environ.get("CSF_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("CSF_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("CSF_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the static-figures check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every interactive figure the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.lines} line(s) across {report.files} file(s), "
          f"{report.figures} interactive figure(s) (scope: {scope}).")
    severity = "error" if fail else "warning"
    for rel, f in report.findings:
        if f.kind == "placeholder":
            msg = ("A note sends readers to the HTML version instead of "
                   f"showing the figure. Fix: {PLACEHOLDER_ADVICE}")
        else:
            msg = f"Interactive figure has no static version. Fix: {HTML_ONLY_ADVICE}"
        print(f"::{severity} file={rel},line={f.line}::{msg}")
    if not report.findings:
        print("Every examined interactive figure has a static version or a stated exemption.")
        return 0
    print(f"\n{len(report.findings)} finding(s): interactive figure(s) with no static version.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
