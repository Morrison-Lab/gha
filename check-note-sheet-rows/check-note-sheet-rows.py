#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a note-sheet table row that holds more than one concept.

The lab's rule (Ezra, 2026-10-22; Morrison-Lab/gha#1164): a note sheet is a
reference table of formulas with brief labels and no prose. Each concept gets
its own row, never two definitions in one row, never notation or assumptions
inside a label, and rows are never merged to save space. The prose rule is
PSW's "Give each concept in a note sheet its own row".

The check reads pipe tables (``| label | formula |``) in the files the globs
match (default ``*note-sheet*.qmd``). It flags a row when:

- the label cell (the first cell) holds a math span (notation in a label),
  unless the label is a link to the term's definition, whose text names the
  term (``[$k$-fold cross-validation](...)``);
- the label cell joins two concepts with a comma or "and" (``Dot product,
  sample mean``);
- a cell outside the first holds two or more math spans joined only by a
  comma, a semicolon or "and" (two definitions in one cell).

A label that ends in ``, ... form``, ``version`` or ``case`` (``Sample MSE,
matrix form``) names one concept in a second form, in a row of its own, and is
not flagged. These are heuristics, so these rules are warn-only by default.

Two prose rules are deterministic, so they are errors whatever ``NSR_FAIL``
says (Ezra, 2026-10-23; gha#1201): a row's label is a sentence (ends in
``.``, ``!`` or ``?``, or runs past six words) or a cell outside the first has
words outside math; and a line outside a table is a paragraph (an inline list
included) rather than a heading, a bold-only label, a link-only line, a div
fence, a table caption or a bullet. Front matter is skipped.

Diff-scoped like ``check-one-div-per-subfile``: only rows added since
``NSR_BASE_REF`` are reported (an added line whose exact text was also deleted
in the same diff is moved, not new). With no base ref, or when the diff cannot
be computed, the check skips with a notice or warning, never a whole-tree scan,
unless ``NSR_WHOLE_TREE=true`` asks for one.

Configuration (environment variables, set by the composite action):
  NSR_BASE_REF      Git ref/SHA to diff against.
  NSR_GLOBS         Space-separated git pathspecs (default '*note-sheet*.qmd').
  NSR_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  NSR_FAIL          "true" => exit 1 on a finding; default "false".
  NSR_WHOLE_TREE    "true" => scan every tracked matching file in full.
"""

import os
import re
import subprocess
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*note-sheet*.qmd"
_DEFAULT_FAIL = False

ADVICE = "give each concept its own row, and put notation or an assumption in a row of its own"
PROSE_ADVICE = ("keep a short label and math only in each row, and put every list "
                "in a table or bullets, as the rme exam formula sheet does")

# -- Parsing -----------------------------------------------------------------

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
ROW_RE = re.compile(r"^\s*\|(.*)\|\s*$")
SEPARATOR_CELL_RE = re.compile(r"^\s*:?-{3,}:?\s*$")
MATH_RE = re.compile(r"(?<!\\)\$(?:[^$\\]|\\.)+\$")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
JOIN_RE = re.compile(r"^\s*(?:,|;|and|,\s*and)\s*$", re.IGNORECASE)
LABEL_JOIN_RE = re.compile(r",|\band\b", re.IGNORECASE)
# ``Sample MSE, matrix form`` names one concept in a second form, in a row of
# its own, as the lds note sheet does; it is not two concepts.
VARIANT_RE = re.compile(r",\s*[\w -]*\b(?:form|version|case)\s*$", re.IGNORECASE)


class Finding(NamedTuple):
    line: int
    reason: str
    hard: bool = False  # a prose finding: an error whatever NSR_FAIL says


# A note sheet holds formulas under brief labels and no prose, and every list is
# a table or bullets (Ezra, 2026-10-22 and 2026-10-23; gha#1201).
LABEL_MAX_WORDS = 6
BOLD_LABEL_RE = re.compile(r"^\*\*[^*]+\*\*$")
LINK_ONLY_RE = re.compile(r"^\[[^\]]*\]\([^)]*\)$")
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
SKIP_LINE_RE = re.compile(r"^\s*(?:#|:::|: |<|>|!\[|\{\{<)")
WORD_RE = re.compile(r"[A-Za-z]")


def split_cells(line: str) -> Optional[List[str]]:
    """Cells of a pipe-table row, or None if the line is not a table row."""
    m = ROW_RE.match(line)
    if not m:
        return None
    body = re.sub(r"(?<!\\)\\\|", "\0", m.group(1))
    math = []
    body = MATH_RE.sub(lambda mm: math.append(mm.group(0)) or "\1", body)
    cells = body.split("|")
    it = iter(math)
    out = []
    for cell in cells:
        cell = re.sub("\1", lambda _: next(it), cell).replace("\0", "|")
        out.append(cell.strip())
    return out


def row_reasons(cells: List[str]) -> List[str]:
    """Reasons a row holds more than one concept, or notation in its label."""
    reasons: List[str] = []
    if not cells or all(SEPARATOR_CELL_RE.match(c) or not c for c in cells):
        return reasons
    label = LINK_RE.sub(r"\1", cells[0])
    if MATH_RE.search(label) and not LINK_RE.search(cells[0]):
        reasons.append("the label holds notation")
    plain = MATH_RE.sub("", label)
    if len(cells) > 1 and LABEL_JOIN_RE.search(VARIANT_RE.sub("", plain)):
        reasons.append("the label joins two concepts")
    for cell in cells[1:]:
        spans = list(MATH_RE.finditer(cell))
        for first, second in zip(spans, spans[1:]):
            if JOIN_RE.match(cell[first.end():second.start()]):
                reasons.append("one cell holds two formulas")
                break
    return reasons


def prose_reasons(cells: List[str]) -> List[str]:
    """Reasons a row holds prose: a sentence label, or words in a formula cell."""
    reasons: List[str] = []
    if not cells or all(SEPARATOR_CELL_RE.match(c) or not c for c in cells):
        return reasons
    label = MATH_RE.sub("", LINK_RE.sub(r"\1", cells[0]))
    if label.rstrip().endswith((".", "!", "?")) or len(label.split()) > LABEL_MAX_WORDS:
        reasons.append("the label is prose")
    for cell in cells[1:]:
        if WORD_RE.search(MATH_RE.sub("", LINK_RE.sub(r"\1", cell))):
            reasons.append("a formula cell holds prose")
            break
    return reasons


def paragraph_reason(raw: str) -> Optional[str]:
    """Why a line outside a table is prose or an inline list, else None."""
    line = raw.strip()
    if not line or SKIP_LINE_RE.match(line) or BOLD_LABEL_RE.match(line):
        return None
    if LINK_ONLY_RE.match(line):
        return None
    if BULLET_RE.match(line):
        spans = list(MATH_RE.finditer(line))
        for first, second in zip(spans, spans[1:]):
            if JOIN_RE.match(line[first.end():second.start()]):
                return "a bullet holds two formulas"
        return None
    return "a paragraph outside a table (put a list in a table or bullets)"


def scan_rows(lines: List[str]) -> List[Finding]:
    """Findings for every table row outside code fences."""
    fence: Optional[Tuple[str, int]] = None
    found: List[Finding] = []
    in_comment = in_item = False
    body_from = 0
    if lines and lines[0].strip() == "---":
        body_from = next((i + 1 for i in range(1, len(lines))
                          if lines[i].strip() == "---"), 0)
    for idx, raw in enumerate(lines):
        if idx < body_from:
            continue
        m = FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        if in_comment:
            in_comment = "-->" not in raw
            continue
        if "<!--" in raw and "-->" not in raw.split("<!--", 1)[1]:
            in_comment = True
            continue
        cells = split_cells(raw)
        if cells is None:
            if not raw.strip():
                in_item = False
                continue
            if in_item and raw[:1] in (" ", "\t") and not BULLET_RE.match(raw):
                continue  # a wrapped bullet continues on an indented line
            in_item = bool(BULLET_RE.match(raw))
            reason = paragraph_reason(raw)
            if reason:
                found.append(Finding(idx + 1, reason, True))
            continue
        in_item = False
        following = split_cells(lines[idx + 1]) if idx + 1 < len(lines) else None
        if following and all(SEPARATOR_CELL_RE.match(c) for c in following):
            continue  # a header row names the columns, not a concept
        reasons = row_reasons(cells)
        if reasons:
            found.append(Finding(idx + 1, "; ".join(reasons)))
        prose = prose_reasons(cells)
        if prose:
            found.append(Finding(idx + 1, "; ".join(prose), True))
    return found


# -- Git plumbing ------------------------------------------------------------

def _run_git(args: List[str]) -> Optional[str]:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    return res.stdout if res.returncode == 0 else None


_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_diff(diff: str) -> Tuple[Dict[str, Dict[int, str]], Set[str]]:
    """Added ``{path: {line_number: text}}`` and the set of deleted texts."""
    added: Dict[str, Dict[int, str]] = {}
    deleted: Set[str] = set()
    path: Optional[str] = None
    old_left = new_left = new_line = 0
    for line in diff.splitlines():
        if old_left > 0 or new_left > 0:
            if line.startswith("+"):
                if path is not None:
                    added[path][new_line] = line[1:]
                new_line += 1
                new_left -= 1
            elif line.startswith("-"):
                deleted.add(line[1:])
                old_left -= 1
            continue
        if line.startswith("+++ "):
            target = line[4:].rstrip("\t")
            path = None if target == "/dev/null" else target[2:] if target.startswith("b/") else target
            if path is not None:
                added.setdefault(path, {})
            continue
        m = _HUNK_RE.match(line)
        if m:
            old_left = int(m.group(1)) if m.group(1) is not None else 1
            new_line = int(m.group(2))
            new_left = int(m.group(3)) if m.group(3) is not None else 1
    return added, deleted


def _glob_to_regex(pat: str) -> "re.Pattern[str]":
    """Translate a path glob to an anchored regex; supports ``**``, ``*``, ``?``."""
    i, n, out = 0, len(pat), []
    while i < n:
        c = pat[i]
        if c == "*":
            if pat[i:i + 2] == "**":
                i += 2
                if pat[i:i + 1] == "/":
                    out.append("(?:.*/)?")
                    i += 1
                else:
                    out.append(".*")
            else:
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def compile_ignores(patterns: List[str]) -> List["re.Pattern[str]"]:
    compiled = []
    for pat in patterns:
        compiled.append(_glob_to_regex(pat))
        if "*" not in pat and "?" not in pat:
            compiled.append(_glob_to_regex(pat.rstrip("/") + "/**"))
    return compiled


def _ignored(rel: str, ignores: List["re.Pattern[str]"]) -> bool:
    return any(r.match(rel) for r in ignores)


def _split_list(value: str) -> List[str]:
    return [p.strip() for p in re.split(r"[,\n]", value) if p.strip()]


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


class Report(NamedTuple):
    findings: List[Tuple[str, int, str, bool]]  # (path, line, reason, hard)
    files: int
    rows: int
    skipped: bool


def _read_lines(path: str) -> Optional[List[str]]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().split("\n")
    except OSError:
        return None
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    """Scan table rows added since ``base_ref``, or every row when whole-tree."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = _run_git(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, 0, True)
        for rel in out.splitlines():
            if rel and not _ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, True)
        base = _run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, True)
        diff = _run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                         base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, True)
        added, deleted = parse_diff(diff)
        for rel, numbered in added.items():
            if _ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if text.strip() and text not in deleted}

    findings: List[Tuple[str, int, str, bool]] = []
    files = rows = 0
    for rel in sorted(wanted):
        content = _read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        for finding in scan_rows(content):
            if keep is None or finding.line in keep:
                findings.append((rel, finding.line, finding.reason, finding.hard))
        rows += sum(1 for i, ln in enumerate(content, 1)
                    if ROW_RE.match(ln) and (keep is None or i in keep))
    return Report(findings, files, rows, False)


def main() -> int:
    base_ref = os.environ.get("NSR_BASE_REF", "").strip()
    globs = os.environ.get("NSR_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("NSR_PATHS_IGNORE", "")))
    fail = _env_flag("NSR_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("NSR_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the note-sheet-rows check for this run "
              f"({reason}; not falling back to a whole-tree scan).")
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.rows} table row(s) across {report.files} file(s) "
          f"(scope: {scope}).")
    for rel, line, reason, hard in report.findings:
        severity = "error" if fail or hard else "warning"
        advice = PROSE_ADVICE if hard else ADVICE
        print(f"::{severity} file={rel},line={line}::Note-sheet row: {reason}. Fix: {advice}")
    if not report.findings:
        print("No note-sheet row holds more than one concept or any prose.")
        return 0
    print(f"\n{len(report.findings)} note-sheet finding(s).")
    return 1 if fail or any(f[3] for f in report.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
