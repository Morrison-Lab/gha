#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a figure that no prose cites, or that sits just outside its example.

The lab's rule (Ezra, 2026-11-02; psw ``chapters/teaching.qmd``): every figure
is discussed and cross-referenced in prose, and a figure specific to one
example or exercise is nested inside that example's or exercise's div.

Two findings, each reported for a figure that holds a line the diff adds:

- **Uncited.** No ``@fig-id`` (or ``](#fig-id)`` link) appears on the page
  outside the figure itself.
- **Unnested.** The figure is not inside an ``#exm-``, ``#exr-`` or ``#sol-``
  div, and the nearest non-blank line before it closes one. A figure shared by
  several examples sits outside every div and follows prose, so it is not hit.

What counts as a figure: a div or image labelled ``{#fig-id}``, or a code chunk
with ``#| label: fig-id``. A figure inside a code fence, an HTML comment or a
blockquote is not counted.

``<!-- figure-placement: allow -->`` on the figure's own line or inside its
div exempts it from both findings.

Design notes, in the model of ``check-exm-figures``, whose parsing and git
helpers come from ``check-one-div-per-subfile``:

- **Diff-scoped by default.** The whole file is parsed, since a citation sits
  far from the figure; a figure is reported only when its span holds an added
  line. No base ref, or an uncomputable diff, skips with a warning.
  ``FPL_WHOLE_TREE=true`` measures a corpus.
- **Per page, not per site.** A citation on another page does not count.
- **Fails by default** (``FPL_FAIL`` defaults to true).

Configuration (environment variables, set by the composite action):
  FPL_BASE_REF, FPL_GLOBS, FPL_PATHS_IGNORE, FPL_FAIL, FPL_WHOLE_TREE.
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
_DEFAULT_FAIL = True

FIG_ID_RE = re.compile(r"\{[^}]*#(fig-[\w:.-]+)")
CHUNK_LABEL_RE = re.compile(r"^\s*#\|\s*label:\s*(fig-[\w:.-]+)")
OWNER_RE = re.compile(r"#(?:exm|exr|sol)-")
ALLOW_RE = re.compile(r"<!--\s*figure-placement:\s*allow\s*-->")

UNCITED = ("Figure {id} is never cited. Fix: cite it with @{id} in a sentence "
           "that says what the reader should see in it")
UNNESTED = ("Figure {id} sits directly after an example or exercise div "
            "instead of inside it. Fix: move it into that div, or add "
            "<!-- figure-placement: allow --> if several examples share it")


class Figure(NamedTuple):
    start: int            # 1-based first line of the figure
    end: int              # 1-based last line of the figure
    ident: str
    owned: bool           # inside an #exm-, #exr- or #sol- div
    after_owner: bool     # nearest non-blank line before it closes one


def scan_figures(lines: List[str]) -> Tuple[List[Figure], List[str]]:
    """Figures outside comments, and the page text with figures' own lines
    blanked, which is where a citation is looked for."""
    fence: Optional[Tuple[str, int, int, Optional[str]]] = None
    in_comment = False
    stack: List[Tuple[int, str, Optional[str]]] = []
    closed_owner: Dict[int, bool] = {}
    figures: List[Figure] = []
    prose = list(lines)
    for idx, raw in enumerate(lines):
        if fence is None:
            raw, in_comment = ods.strip_comments(raw, in_comment)
        m = ods.FENCE_RE.match(raw)
        if fence is not None:
            if fence[3] is None:
                lab = CHUNK_LABEL_RE.match(raw)
                if lab:
                    fence = (fence[0], fence[1], fence[2], lab.group(1))
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                if fence[3]:
                    figures.append(_make(fence[2], idx + 1, fence[3], stack,
                                         after_owner(fence[2], lines, closed_owner)))
                    for k in range(fence[2] - 1, idx + 1):
                        prose[k] = ""
                fence = None
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)), idx + 1, None)
            continue
        if not raw.strip():
            continue
        dm = ods.DIV_RE.match(raw)
        if dm:
            if dm.group(2):
                fm = FIG_ID_RE.search("{" + dm.group(2) + "}") if "#fig-" in dm.group(2) else None
                stack.append((idx + 1, dm.group(2), fm.group(1) if fm else None))
            elif stack:
                start, attrs, fid = stack.pop()
                if fid:
                    figures.append(_make(start, idx + 1, fid, stack,
                                         after_owner(start, lines, closed_owner)))
                    for k in range(start - 1, idx + 1):
                        prose[k] = ""
                else:
                    closed_owner[idx + 1] = bool(OWNER_RE.search(attrs))
            continue
        im = FIG_ID_RE.search(raw)
        if im and "![" in raw:
            figures.append(_make(idx + 1, idx + 1, im.group(1), stack,
                                 after_owner(idx + 1, lines, closed_owner)))
            prose[idx] = ""
    return figures, prose


def after_owner(start: int, lines: List[str],
                closed_owner: Dict[int, bool]) -> bool:
    """Whether the nearest non-blank line before ``start`` closed an owner."""
    k = start - 2
    while k >= 0 and not lines[k].strip():
        k -= 1
    return closed_owner.get(k + 1, False)


def _make(start: int, end: int, ident: str,
          stack: List[Tuple[int, str, Optional[str]]], after: bool) -> Figure:
    owned = any(OWNER_RE.search(a) for _, a, _ in stack)
    return Figure(start, end, ident, owned, after and not owned)


def cited(ident: str, prose: List[str]) -> bool:
    pat = re.compile(r"@" + re.escape(ident) + r"(?![\w:.-]*\w)|\]\(#" + re.escape(ident) + r"\)")
    return any(pat.search(line) for line in prose)


def scan_file(lines: List[str], keep: Optional[Set[int]]
              ) -> Tuple[List[Tuple[Figure, str]], int]:
    """(figure, message) for each finding on a kept line, and figures seen."""
    figures, prose = scan_figures(lines)
    out: List[Tuple[Figure, str]] = []
    for fig in figures:
        if any(ALLOW_RE.search(line) for line in lines[fig.start - 1:fig.end]):
            continue
        if keep is not None and not any(fig.start <= n <= fig.end for n in keep):
            continue
        if not cited(fig.ident, prose):
            out.append((fig, UNCITED.format(id=fig.ident)))
        if fig.after_owner:
            out.append((fig, UNNESTED.format(id=fig.ident)))
    return out, len(figures)


class Report(NamedTuple):
    findings: List[Tuple[str, int, str]]  # (path, line, message)
    files: int
    lines: int
    figures: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: list,
              whole_tree: bool) -> Report:
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = diffscope.run_git(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, 0, 0, True)
        for rel in out.splitlines():
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
    files = lines = seen = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        found, n = scan_file(content, keep)
        seen += n
        findings.extend((rel, fig.start, msg) for fig, msg in found)
    return Report(findings, files, lines, seen, False)


def main() -> int:
    base_ref = os.environ.get("FPL_BASE_REF", "").strip()
    globs = os.environ.get("FPL_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = diffscope.compile_ignores(
        diffscope.split_list(os.environ.get("FPL_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("FPL_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("FPL_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the figure-placement check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every figure the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s), "
        f"{report.figures} figure(s) (scope: {scope})."
    )
    severity = "error" if fail else "warning"
    for rel, line, msg in report.findings:
        print(f"::{severity} file={rel},line={line}::{msg}")
    if not report.findings:
        print("Every examined figure is cited and nested.")
        return 0
    print(f"\n{len(report.findings)} figure finding(s).")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
