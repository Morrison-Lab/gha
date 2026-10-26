#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a div that asks for a picture but has no figure.

The lab's rule (Ezra, 2026-10-26): every div whose title mentions
visualization (visualize, visualizing, visualization) must have a
corresponding figure, and for an exercise the solution includes it.
The trigger is wider than the one word, so the rule's own example,
"Mark every zero-gradient point on a surface", is caught:

- for an exercise or example, a title matching ``TITLE_RE``: visuali[sz]\*,
  plot, sketch, draw, contour, picture, diagram, or "mark ... points,
  curves, surfaces, or regions";
- for any other div, a title that says visuali[sz]\*;
- for an exercise (``#exr-``), a prompt that says sketch, draw, plot, or
  visuali[sz]\* outside its code fences.

A div's title is the text of the first heading inside it (``#### Title``) or
its ``title="..."`` attribute. The divs checked carry an exercise, example,
definition, result or remark id (``#exr-``, ``#exm-``, ``#def-``, ``#thm-``,
``#lem-``, ``#prp-``, ``#cor-``, ``#rem-``); a ``#fig-`` or ``#sol-`` div is
the figure or the answer itself and is never the subject.

What counts as a figure is what ``check-exm-figures`` counts: an image, a
``fig-`` labeled chunk or div, an ``@fig-`` reference, or an include of a
``_fig`` subfile. For an exercise, the figure may also be in

- a ``#sol-<slug>`` div in the same file, where ``<slug>`` is the exercise's
  id without its ``exr-`` prefix;
- another file of the same exercise family in the same folder:
  ``_exr-a.qmd``, ``_sol-a.qmd``, ``_exr-a-part2.qmd`` and ``_sol-a-part2.qmd``
  share the base name ``a``, since a multi-part exercise shows its figure once.

A div is exempt when it holds ``<!-- no-figure: reason -->`` with a
non-empty reason, which is the escape for a false positive.
Whole paths are exempt through ``paths-ignore``.

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
# A title asks for a picture: a visual verb or noun, or "mark ... points" and
# the like. "graph" is left out on purpose: it names a data structure and the
# graph of a function as often as a plot.
TITLE_RE = re.compile(
    r"visuali[sz]\w*"
    r"|\b(?:plots?|plotting|sketch\w*|draw|drawing|contours?|pictures?|diagrams?)\b"
    r"|\bmark\b.*\b(?:points?|curves?|surfaces?|regions?)\b",
    re.IGNORECASE,
)
# A definition, theorem or remark names a plot type ("Boxplot") or a contour
# without needing a figure inside it, since the example that follows it has
# one, so only the word visualization asks them for a figure.
RESULT_TITLE_RE = re.compile(r"visuali[sz]\w*", re.IGNORECASE)
# An exercise's prompt asks the reader to produce a picture. "draw" alone is
# left out ("draw a sample"), and "plot" counts as a verb only.
PROMPT_RE = re.compile(
    r"\b(?:sketch\w*|visuali[sz]\w*)\b"
    r"|(?:^|[.!?:]\s+|\b(?:to|and|or|then|you|can|should|will)\s+)plot\b"
    r"|\bdraw\s+(?:the|a|an|one|two|each)?\s*"
    r"(?:real\s+)?(?:dendrograms?|trees?|diagrams?|pictures?|figures?|graphs?"
    r"|contours?|curves?|lines?)\b",
    re.IGNORECASE | re.MULTILINE,
)
RELATED_RE = re.compile(r"^_(?:exr|sol)-(.+?)(?:-part\d+)?\.qmd$")
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


def family(path: str) -> str:
    """The base name shared by an exercise, its solution and its parts."""
    m = RELATED_RE.match(os.path.basename(path))
    return m.group(1) if m else ""


def related_files(path: str) -> List[List[str]]:
    """Lines of the ``_exr-``/``_sol-`` files of the same exercise.

    ``_exr-a.qmd`` is related to ``_sol-a.qmd``, ``_exr-a-part2.qmd`` and the
    rest of its family: a multi-part exercise shows its figure once.
    """
    base = family(path)
    folder = os.path.dirname(path) or "."
    if not base or not os.path.isdir(folder):
        return []
    found = []
    for name in sorted(os.listdir(folder)):
        if name != os.path.basename(path) and family(name) == base:
            content = ods._read_lines(os.path.join(folder, name))
            if content is not None:
                found.append(content)
    return found


def asks_for_picture(lines: List[str], div: Div, subject: str) -> bool:
    """Whether the title, or an exercise's prompt, asks for a picture."""
    title = title_of(lines, div)
    if subject.startswith(("exr-", "exm-")):
        if TITLE_RE.search(title):
            return True
    elif RESULT_TITLE_RE.search(title):
        return True
    if not subject.startswith("exr-"):
        return False
    prompt = []
    in_code = False
    for line in lines[div.start:div.end - 1]:
        if ods.FENCE_RE.match(line):
            in_code = not in_code
        elif not in_code and not HEADING_RE.match(line):
            prompt.append(line)
    return bool(PROMPT_RE.search("\n".join(prompt)))


def has_figure_or_exemption(body: List[str]) -> bool:
    return exf.has_figure(body) or exf.is_exempt(body)


def check_lines(lines: List[str], path: str, keep: Optional[Set[int]],
                related: Optional[List[List[str]]] = None
                ) -> Tuple[List[Div], int]:
    """Divs that ask for a picture but have none, holding a kept line.

    Also returns how many divs ask for a picture. ``related`` is the lines of
    the exercise's other files; it defaults to ``related_files(path)``.
    """
    divs = scan_divs(lines)
    if related is None:
        related = related_files(path)
    same_file_solutions = {
        m.group(1): d for d in divs
        for m in [re.search(r"#(sol-[\w:.-]+)", d.attrs)] if m
    }
    missing: List[Div] = []
    seen = 0
    for div in divs:
        subject = SUBJECT_RE.search(div.attrs)
        if not subject or not asks_for_picture(lines, div, subject.group(1)):
            continue
        seen += 1
        if has_figure_or_exemption(lines[div.start - 1:div.end]):
            continue
        if subject.group(1).startswith("exr-"):
            if any(has_figure_or_exemption(lines[d.start - 1:d.end])
                   for d in same_file_solutions.values()):
                continue
            if any(has_figure_or_exemption(other) for other in related):
                continue
        if keep is None or any(div.start <= n <= div.end for n in keep):
            missing.append(div)
    return missing, seen


def format_message(attrs: str) -> str:
    ident = SUBJECT_RE.search(attrs)
    name = "#" + ident.group(1) if ident else "div"
    return f"Div {name} asks for a picture (a visual word in its title or prompt) but has no figure. Fix: {ADVICE}"


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
        # A changed solution file puts the exercise family's prompts in scope:
        # they hold no added line, but their figure may have been removed.
        for rel in list(wanted):
            folder, name = os.path.split(rel)
            base = family(name) if name.startswith("_sol-") else ""
            if not base or not os.path.isdir(folder or "."):
                continue
            for other in sorted(os.listdir(folder or ".")):
                if other.startswith("_exr-") and family(other) == base:
                    twin = os.path.join(folder, other)
                    if twin not in wanted:
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
