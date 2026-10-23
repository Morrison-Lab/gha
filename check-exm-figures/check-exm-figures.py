#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag an example div (``#exm-``) that has no figure.

The lab's rule (Ezra, 2026-10-23; Morrison-Lab/gha#1193): nearly every
example div gets a figure of its data, model or results, so the notes show
what the example computes. A justified exception carries a reason.

What counts as a figure inside the div:

- a Markdown image (``![alt](path)``) or an ``<img`` tag;
- a div or chunk labelled ``fig-`` (``{#fig-...}``, ``#| label: fig-...``,
  ``#| fig-cap:`` or ``#| fig-alt:``);
- a cross-reference to a figure (``@fig-...``);
- an include of a figure subfile (``{{< include ..._fig.qmd >}}``).

An example is exempt when its div holds an HTML comment of the form
``<!-- no-figure: reason -->`` with a non-empty reason. A comment with no
reason does not exempt it. Whole paths are exempt through ``paths-ignore``.

What is not counted: a div inside a code fence, an HTML comment or a
blockquote, and the divs an ``include`` shortcode may pull in at render time.

Design notes, in the model of ``check-one-div-per-subfile``, whose parsing and
git helpers this script imports rather than copies:

- **Diff-scoped by default.** An example div is reported only when it holds a
  line the diff adds, so existing examples are never reflagged. The whole
  file is parsed, since a div opens far above the line that changed. An added
  line whose exact text was also deleted in the same diff is moved, not new,
  and a blank added line is not content.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``EXF_WHOLE_TREE=true`` scans
  every tracked file, which measures how many examples lack a figure.
- **Blocking by default** (``EXF_FAIL`` defaults to true; all annotations fail CI).
- **The search space is reported**: files, lines, examples and examples with
  a figure or an exemption.

Configuration (environment variables, set by the composite action):
  EXF_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  EXF_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  EXF_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  EXF_FAIL          "false" => warn only; default "true".
  EXF_WHOLE_TREE    "true" => scan every tracked matching file in full.
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

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = True

ADVICE = (
    "add a figure of the example's data, model or results, or add "
    "<!-- no-figure: reason --> inside the div"
)

EXM_RE = re.compile(r"#exm-")
FIGURE_RES = [re.compile(p) for p in (
    r"!\[",
    r"<img\b",
    r"\{#fig-",
    r"^\s*#\|\s*(?:label:\s*fig-|fig-cap\b|fig-alt\b)",
    r"@fig-",
    r"\{\{<\s*include\s+\S*_fig\S*\.qmd",
)]
EXEMPT_RE = re.compile(r"<!--\s*no-figure:\s*(?!-->)\S")


class Example(NamedTuple):
    start: int  # 1-based line of the opening fence
    end: int    # 1-based line of the closing fence
    attrs: str


def scan_examples(lines: List[str]) -> List[Example]:
    """Every ``#exm-`` div outside code fences and HTML comments."""
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    stack: List[Tuple[int, str]] = []
    found: List[Example] = []
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
            if EXM_RE.search(attrs):
                found.append(Example(start, idx + 1, attrs))
    return found


def has_figure(body: List[str]) -> bool:
    return any(r.search(line) for line in body for r in FIGURE_RES)


def is_exempt(body: List[str]) -> bool:
    return any(EXEMPT_RE.search(line) for line in body)


def scan_file(lines: List[str], keep: Optional[Set[int]]) -> Tuple[List[Example], int]:
    """Examples without a figure that hold a kept line, and examples seen."""
    missing: List[Example] = []
    examples = scan_examples(lines)
    for ex in examples:
        body = lines[ex.start - 1:ex.end]
        if has_figure(body) or is_exempt(body):
            continue
        if keep is None or any(ex.start <= n <= ex.end for n in keep):
            missing.append(ex)
    return missing, len(examples)


def format_message(attrs: str) -> str:
    ident = re.search(r"#exm-[\w:.-]+", attrs)
    name = ident.group(0) if ident else "example"
    return f"Example {name} has no figure. Fix: {ADVICE}"


class Report(NamedTuple):
    findings: List[Tuple[str, int, str]]  # (path, opening line, attrs)
    files: int
    lines: int
    examples: int
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
    files = lines = examples = 0
    for rel in sorted(wanted):
        content = ods._read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        missing, seen = scan_file(content, keep)
        examples += seen
        findings.extend((rel, ex.start, ex.attrs) for ex in missing)
    return Report(findings, files, lines, examples, False)


def main() -> int:
    base_ref = os.environ.get("EXF_BASE_REF", "").strip()
    globs = os.environ.get("EXF_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = ods.compile_ignores(ods._split_list(os.environ.get("EXF_PATHS_IGNORE", "")))
    fail = ods._env_flag("EXF_FAIL", _DEFAULT_FAIL)
    whole_tree = ods._env_flag("EXF_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the example-figure check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every example the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s), "
        f"{report.examples} example div(s) (scope: {scope})."
    )
    severity = "error" if fail else "warning"
    for rel, line, attrs in report.findings:
        print(f"::{severity} file={rel},line={line}::{format_message(attrs)}")
    if not report.findings:
        print("Every examined example has a figure or a stated exemption.")
        return 0
    print(f"\n{len(report.findings)} example div(s) have no figure.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
