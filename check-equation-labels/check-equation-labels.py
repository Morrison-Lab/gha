#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a ``$$ ... $$`` display equation that carries no ``{#eq-...}`` label.

The lab labels every display equation, so that it gets a number and a stable
URL (ai-config AGENTS.md, "Graph and display equation defaults"). The
``equation-anchors`` filter adds a permalink only to a labeled equation, so an
unlabeled one has no anchor to link to. Quarto reads the label from the same
line as the closing ``$$``:

    $$
    H(X) = -\sum_x p(x) \log p(x)
    $$ {#eq-entropy}

Moved here from Morrison-Lab/ids#201, which labeled all 215 of that repo's
display equations and added this check as a repo-local tool.

What is not counted: ``$$`` inside a code fence, a code span, or an HTML
comment, and an escaped ``\$``. Raw LaTeX environments (``\begin{equation}``)
are not display equations here: Quarto numbers only ``$$`` math.

``<!-- check-equation-labels: allow: <reason> -->`` on the equation's opening
line, or on the line before it, exempts it. A pragma with no reason exempts
nothing.

Design notes, in the model of ``check-lone-subfloats``:

- **Diff-scoped by default.** An equation is reported when a line of it, from
  the opening ``$$`` through the closing one, is a line the diff adds. The
  whole file is parsed, since an equation opens above the line that changed.
  A moved line (deleted with the same text) is not new, so labeling one
  equation does not reflag its unlabeled neighbours.
- **Skip, not fall back.** With no base ref, or an uncomputable diff, the
  check skips with a warning. ``CEL_WHOLE_TREE=true`` measures a corpus.
- **Fails by default** (``CEL_FAIL`` defaults to true).

Configuration (environment variables, set by the composite action):
  CEL_BASE_REF, CEL_GLOBS, CEL_PATHS_IGNORE, CEL_FAIL, CEL_WHOLE_TREE.
"""

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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402
import mdmask  # noqa: E402

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = True

# A label in the attribute block right after the closing $$.
LABEL_RE = re.compile(r"^[ \t]*\{[^}]*#eq-[\w:.-]+")
ALLOW_RE = re.compile(r"<!--\s*check-equation-labels:\s*allow:\s*(\S[^>]*?)\s*-->")


class Finding(NamedTuple):
    start: int  # 1-based line of the opening $$
    end: int    # 1-based line of the closing $$
    body: str   # the equation's text, whitespace collapsed


def _delimiters(line: str) -> List[int]:
    """Columns where a ``$$`` delimiter starts; a backslash escapes a ``$``."""
    cols, pos, n = [], 0, len(line)
    while pos < n:
        ch = line[pos]
        if ch == "\\":
            pos += 2
            continue
        if line.startswith("$$", pos):
            cols.append(pos)
            pos += 2
            continue
        pos += 1
    return cols


def scan_file(lines: List[str]) -> List[Finding]:
    """Each unlabeled display equation in a document's lines."""
    findings: List[Finding] = []
    fence: Optional[str] = None
    in_comment = False
    open_at: Optional[Tuple[int, int]] = None  # (line index, column after $$)
    body: List[str] = []
    for i, raw in enumerate(lines):
        if fence is not None:
            m = mdmask.FENCE_RE.match(raw)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                    and not m.group(2):
                fence = None
            continue
        text, in_comment = mdmask.mask_markdown_line(raw, in_comment)
        if open_at is None:
            m = mdmask.FENCE_RE.match(text)
            if m:
                fence = m.group(1)
                continue
        cursor = 0
        for col in _delimiters(text):
            if open_at is None:
                open_at = (i, col + 2)
                body = []
                cursor = col + 2
                continue
            start_line, start_col = open_at
            body.append(text[start_col if start_line == i else cursor:col])
            if not LABEL_RE.match(text[col + 2:]) and not _allowed(lines, start_line):
                findings.append(Finding(start_line + 1, i + 1,
                                        " ".join(" ".join(body).split())))
            open_at, cursor = None, col + 2
        if open_at is not None:
            start_line, start_col = open_at
            body.append(text[start_col:] if start_line == i else text)
            # Pandoc ends display math at a blank line, so a stray $$ does not
            # swallow the rest of the file.
            if not text.strip() and start_line != i:
                open_at = None
    return findings


def _allowed(lines: List[str], start: int) -> bool:
    """Whether an allow pragma with a reason sits on or just above the opener."""
    for j in (start, start - 1):
        if 0 <= j < len(lines) and ALLOW_RE.search(lines[j]):
            return True
    return False


def format_message(f: Finding) -> str:
    excerpt = f.body[:70] + ("..." if len(f.body) > 70 else "")
    return (f"Display equation has no {{#eq-...}} label, so it gets no number "
            f"and no anchor: put one after the closing $$, such as "
            f"$$ ... $$ {{#eq-name}}. Equation: {excerpt}")


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
    files: int
    lines: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: list,
              whole_tree: bool) -> Report:
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = diffscope.git_paths(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, 0, True)
        for rel in out:
            if rel and not diffscope.ignored(rel, ignores):
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
                           if text.strip() and text not in deleted}

    findings: List[Tuple[str, Finding]] = []
    files = lines = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        for f in scan_file(content):
            if keep is None or any(f.start <= n <= f.end for n in keep):
                findings.append((rel, f))
    return Report(findings, files, lines, False)


def main() -> int:
    base_ref = os.environ.get("CEL_BASE_REF", "").strip()
    globs = os.environ.get("CEL_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = diffscope.compile_ignores(
        diffscope.split_list(os.environ.get("CEL_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("CEL_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("CEL_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        if whole_tree:
            reason = "could not list the tracked files"
        elif base_ref:
            reason = f"could not diff against '{base_ref}'"
        else:
            reason = "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the equation-label check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every unlabeled equation the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.lines} line(s) across {report.files} file(s) "
          f"(scope: {scope}).")
    severity = "error" if fail else "warning"
    for rel, f in report.findings:
        print(f"::{severity} file={rel},line={f.start}::{format_message(f)}")
    if not report.findings:
        print("Every examined display equation is labeled.")
        return 0
    print(f"\n{len(report.findings)} unlabeled display equation(s).")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
