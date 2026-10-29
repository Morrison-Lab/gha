#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a contrast ("X, not Y") in a definition, remark or note that cites no source.

The lab's rule (Ezra, 2026-10-28; Morrison-Lab/psw): a contrast the text keeps
must say who holds the other reading, with a source, so it is not a straw man.
If no source or reader holds the reading, the contrast is deleted. Example:
"Statistics uses predictor for a feature, not for a model" (lds#1565).

Whether anyone holds the other reading is a fact about the literature, so no
script can decide it. This check is a heuristic prompt for the author:
it flags the phrasing that usually signals such a contrast, in a ``#def-``,
``#rem-`` or ``#note-`` div that holds no citation.

What is flagged, in the prose of such a div: ", not for/as/a/an/the",
"does not mean", "do not mean", "not to be confused with", "is not a/an" and
"rather than a/an". The finding sits on the line that holds the phrase.

What is not flagged:

- a div that holds a citation (``[@key``), since the source is the explanation;
- lines inside code fences, display math or HTML comments, and inline code;
- a line carrying ``<!-- check-unexplained-contrasts: allow -->``;
- a div whose id is not ``def-``, ``rem-`` or ``note-``.

The phrase list is noisy by design ("is not a tree" is a fine statement), which
is why the check is warn-only by default.

Design notes, in the model of ``check-def-commentary``:

- **Diff-scoped by default.** Only an added line is reported. The whole file
  is parsed, since the div opens far above the line that changed. An added
  line whose exact text was also deleted in the diff counts as moved.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``UCT_WHOLE_TREE=true`` scans the
  whole tree, which measures how many existing contrasts lack a source.
- **Warn-only by default** (``UCT_FAIL`` defaults to false).

Configuration (environment variables, set by the composite action):
  UCT_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  UCT_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  UCT_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  UCT_FAIL          "true" => error annotations and a failing exit;
                    default "false".
  UCT_WHOLE_TREE    "true" => scan every tracked matching file in full.
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

DEFAULT_GLOBS = "*.qmd"
_DEFAULT_FAIL = False
ALLOW_MARKER = "check-unexplained-contrasts: allow"

ADVICE = (
    "say who holds the other reading and cite a source "
    "(psw: Do not rule out readings no reader would make), delete the "
    "contrast if nobody holds it, or add "
    "<!-- check-unexplained-contrasts: allow --> if it is a plain statement"
)

CONTRAST_RE = re.compile(
    r"(,\s+not\s+(?:for|as|a|an|the)\b"
    r"|\bdoes not mean\b|\bdo not mean\b"
    r"|\bnot to be confused with\b"
    r"|\bis not (?:a|an)\b"
    r"|\brather than (?:a|an)\b)",
    re.IGNORECASE,
)
CITATION_RE = re.compile(r"\[-?@[A-Za-z0-9_]")
CONTRAST_ID_RE = re.compile(r"#(?:def|rem|note)-")

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")


class Finding(NamedTuple):
    line: int
    phrase: str


class _Frame:
    """One open div: whether it is read, its candidate hits, its citation."""

    def __init__(self, read: bool) -> None:
        self.read = read
        self.hits: List[Finding] = []
        self.cited = False


def strip_comment(raw: str, in_comment: bool) -> Tuple[str, bool]:
    """Drop HTML comment text from one line; say whether one stays open."""
    out, i = [], 0
    while i < len(raw):
        if in_comment:
            end = raw.find("-->", i)
            if end < 0:
                return "".join(out), True
            i, in_comment = end + 3, False
        else:
            start = raw.find("<!--", i)
            if start < 0:
                out.append(raw[i:])
                break
            out.append(raw[i:start])
            i, in_comment = start + 4, True
    return "".join(out), in_comment


def scan_contrasts(lines: List[str]) -> List[Finding]:
    """Contrast phrases in a ``def-``/``rem-``/``note-`` div with no citation."""
    findings: List[Finding] = []
    stack: List[_Frame] = []
    fence: Optional[Tuple[str, int]] = None
    in_math = in_comment = False
    for idx, original in enumerate(lines):
        raw = original
        if fence is None:
            raw, in_comment = strip_comment(raw, in_comment)
        m = FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        if raw.count("$$") % 2 == 1:
            in_math = not in_math
            continue
        if in_math:
            continue
        dm = DIV_RE.match(raw)
        if dm:
            if dm.group(2):
                stack.append(_Frame(bool(CONTRAST_ID_RE.search(dm.group(2)))))
            elif stack:
                frame = stack.pop()
                if frame.read and not frame.cited:
                    findings.extend(frame.hits)
            continue
        if not stack or not stack[-1].read:
            continue
        if CITATION_RE.search(raw):
            stack[-1].cited = True
        if ALLOW_MARKER in original:
            continue
        prose = CODE_SPAN_RE.sub(" ", raw)
        hit = CONTRAST_RE.search(prose)
        if hit:
            stack[-1].hits.append(Finding(idx + 1, hit.group(1).strip(", ")))
    # A file with no div: nothing is read, so nothing is flagged.
    return sorted(findings)


def format_message(phrase: str) -> str:
    return (f"Contrast (\"{phrase}\") in a definition, remark or note that "
            f"cites no source; a kept contrast must say why a reader would "
            f"hold the other reading. Fix: {ADVICE}")


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
    findings: List[Tuple[str, Finding]]
    files: int
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
    """Scan files with an added line since ``base_ref``, or all when whole-tree."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = _run_git(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, True)
        for rel in out.splitlines():
            if rel and not _ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, True)
        base = _run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, True)
        diff = _run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                         base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, True)
        added, deleted = parse_diff(diff)
        for rel, numbered in added.items():
            if _ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if text.strip() and text not in deleted}

    findings: List[Tuple[str, Finding]] = []
    files = 0
    for rel in sorted(wanted):
        content = _read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        for found in scan_contrasts(content):
            if keep is None or found.line in keep:
                findings.append((rel, found))
    return Report(findings, files, False)


def main() -> int:
    base_ref = os.environ.get("UCT_BASE_REF", "").strip()
    globs = os.environ.get("UCT_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("UCT_PATHS_IGNORE", "")))
    fail = _env_flag("UCT_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("UCT_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the unexplained-contrasts check for this run "
              f"({reason}; not falling back to a whole-tree scan, which would "
              f"reflag every contrast the corpus already carries).")
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.files} file(s) (scope: {scope}).")
    severity = "error" if fail else "warning"
    for rel, found in report.findings:
        print(f"::{severity} file={rel},line={found.line}::{format_message(found.phrase)}")
    if not report.findings:
        print("No unexplained contrast found.")
        return 0
    print(f"\n{len(report.findings)} unexplained contrast(s).")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
