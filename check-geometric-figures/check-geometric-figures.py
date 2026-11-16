#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a geometric claim in prose that has no figure nearby.

The lab's rule (Ezra, 2026-11-16): every geometric claim in course notes,
such as "the loss term has elliptical contours" or "the penalty has circular
contours centered at the origin", is paired with a graphical illustration
nearby.

A line is a geometric claim when its prose (outside code fences, HTML
comments, and ``$...$`` math) uses geometric vocabulary matched by
``CLAIM_RE``: contour, ellipse, circle, level set or curve, tangent line,
hyperplane, decision boundary, perpendicular, "projects onto", "geometric
interpretation", "right angle". The list is deliberately narrow: convex,
angle, orthogonal and projection alone are ordinary algebra and are not
matched.

The claim has a figure when one of these lies within ``GEOM_WINDOW`` lines
(default 40) of it in the same file, or anywhere in a div that encloses it:
an image, a ``fig-`` labeled chunk or div, an ``@fig-`` reference, or an
include of a ``_fig`` subfile (the test ``check-exm-figures`` uses).
``<!-- no-figure: reason -->`` in the same span exempts a claim that no
figure can show; the reason is required.

Why a check can only approximate the rule: it sees that *a* figure is near
the claim, not that the figure shows *this* claim. The Claude review prompt
carries the second half (see psw ``chapters/teaching.qmd``).

Design notes, as in ``check-visualization-figures``, whose div parser this
script reuses:

- **Diff-scoped by default**: only a claim on a line the diff adds is
  reported; an added line whose exact text was also deleted is moved.
- **One finding per paragraph**: the first claim line of a paragraph.
- **Skip, not fall back** when there is no base to diff against;
  ``GEOM_WHOLE_TREE=true`` scans every tracked file.
- **Blocking by default** (``GEOM_FAIL`` defaults to true).

Configuration (environment variables, set by the composite action):
  GEOM_BASE_REF      Git ref/SHA to diff against.
  GEOM_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  GEOM_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  GEOM_FAIL          "false" => warn only; default "true".
  GEOM_WHOLE_TREE    "true" => scan every tracked matching file in full.
  GEOM_WINDOW        Lines either side of a claim searched for a figure.
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


sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402

viz = _load_sibling("check-visualization-figures")
exf = _load_sibling("check-exm-figures")
ods = viz.ods

DEFAULT_GLOBS = "*.qmd"
DEFAULT_WINDOW = 40
_DEFAULT_FAIL = True

ADVICE = (
    "add a figure that shows it within a few lines (a plot, a diagram, or a "
    "`_fig` include), or add <!-- no-figure: reason --> if nothing can show it"
)

CLAIM_RE = re.compile(
    r"\bcontours?\b"
    r"|\bellips\w*|\belliptical\b"
    r"|\bcircles?\b|\bcircular\b"
    r"|\blevel\s+(?:sets?|curves?|surfaces?)\b"
    r"|\btangent\s+(?:to|line|plane|at)\b"
    r"|\bhyperplanes?\b"
    r"|\bdecision\s+boundar(?:y|ies)\b"
    r"|\bperpendicular\b"
    r"|\bproject(?:s|ed|ion)?\s+onto\b"
    r"|\bgeometric(?:ally)?\s+(?:interpretation|picture|view)\b|\bgeometrically\b"
    r"|\bright\s+angles?\b",
    re.IGNORECASE,
)
INLINE_MATH_RE = re.compile(r"\$[^$\n]*\$")
EXEMPT_RE = re.compile(r"<!--\s*no-figure:\s*(?!-->)\S")


def prose_of(lines: List[str]) -> List[Optional[str]]:
    """Each line's prose, or None inside code fences, comments, display math."""
    out: List[Optional[str]] = []
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    in_math = False
    for raw in lines:
        if fence is None:
            text, in_comment = ods.strip_comments(raw, in_comment)
        else:
            text = raw
        m = ods.FENCE_RE.match(text)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            out.append(None)
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            out.append(None)
            continue
        if text.count("$$") % 2 == 1:
            in_math = not in_math
            out.append(None)
            continue
        if in_math or ods.DIV_RE.match(text) or viz.HEADING_RE.match(text):
            out.append(None)
            continue
        out.append(INLINE_MATH_RE.sub(" ", text))
    return out


def has_figure_or_exemption(body: List[str]) -> bool:
    return exf.has_figure(body) or any(EXEMPT_RE.search(x) for x in body)


def check_lines(lines: List[str], keep: Optional[Set[int]],
                window: int = DEFAULT_WINDOW) -> Tuple[List[int], int]:
    """1-based lines of unpaired claims (first per paragraph) and claim count."""
    prose = prose_of(lines)
    divs = viz.scan_divs(lines)
    missing: List[int] = []
    seen = 0
    paragraph_done = False
    for idx, text in enumerate(prose):
        if not lines[idx].strip():
            paragraph_done = False
            continue
        if text is None or not CLAIM_RE.search(text):
            continue
        seen += 1
        n = idx + 1
        if paragraph_done or (keep is not None and n not in keep):
            continue
        near = lines[max(0, idx - window):idx + window + 1]
        if has_figure_or_exemption(near):
            continue
        if any(d.start <= n <= d.end
               and has_figure_or_exemption(lines[d.start - 1:d.end])
               for d in divs):
            continue
        missing.append(n)
        paragraph_done = True
    return missing, seen


def format_message(text: str) -> str:
    match = CLAIM_RE.search(text)
    word = match.group(0) if match else "geometric word"
    return (f"Geometric claim (\"{word}\") has no figure nearby. "
            f"Fix: {ADVICE}")


class Report(NamedTuple):
    findings: List[Tuple[str, int, str]]  # (path, line, line text)
    files: int
    lines: int
    claims: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: list,
              whole_tree: bool, window: int) -> Report:
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

    findings: List[Tuple[str, int, str]] = []
    files = lines = claims = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        missing, seen = check_lines(content, keep, window)
        claims += seen
        findings.extend((rel, n, content[n - 1]) for n in missing)
    return Report(findings, files, lines, claims, False)


def main() -> int:
    base_ref = os.environ.get("GEOM_BASE_REF", "").strip()
    globs = os.environ.get("GEOM_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = diffscope.compile_ignores(
        diffscope.split_list(os.environ.get("GEOM_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("GEOM_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("GEOM_WHOLE_TREE", False)
    try:
        window = int(os.environ.get("GEOM_WINDOW", DEFAULT_WINDOW))
    except ValueError:
        window = DEFAULT_WINDOW

    report = run_check(base_ref, globs, ignores, whole_tree, window)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the geometric-figure check for this run "
              f"({reason}; not falling back to a whole-tree scan).")
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.lines} line(s) across {report.files} file(s), "
          f"{report.claims} geometric claim line(s) (scope: {scope}).")
    severity = "error" if fail else "warning"
    for rel, line, text in report.findings:
        print(f"::{severity} file={rel},line={line}::{format_message(text)}")
    if not report.findings:
        print("Every examined geometric claim has a figure nearby or a stated exemption.")
        return 0
    print(f"\n{len(report.findings)} geometric claim(s) have no figure nearby.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
