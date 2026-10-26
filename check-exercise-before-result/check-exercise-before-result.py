#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a result div that no exercise-and-solution pair precedes.

The lab's rule (Ezra, 2026-10-26; Morrison-Lab/gha#1242): every result div
(``#thm-``, ``#lem-``, ``#cor-`` or ``#prp-``) that is added or edited has an
exercise and its solution just before it. The exercise asks the student to
prove the result, and the result div then states what the solution showed (see
``check-solution-citations`` for the matching citation rule).

How it reads a chapter: it flattens a ``.qmd`` file into a sequence of blocks,
following ``{{< include ... >}}`` calls into their files. A block is an include
or a top-level ``::: {#xxx-...}`` div; its kind is the prefix of the file name
(``_exr-name.qmd``) or of the div id. Blank lines, slide breaks and HTML
comments are skipped. A result block passes when the two blocks before it are an
exercise and then a solution. Several ``_exr-``/``_sol-`` pairs in a row are
fine: only the last pair is looked at.

What is checked: only a result whose source file has a line a diff adds (for
an include, the included file; for an inline div, the chapter itself). The
escape hatch is ``<!-- check-exercise-before-result: allow -->`` on the first
line of the result's file or div, for a result that no exercise can precede
(a restated textbook theorem, say).

Design notes, in the model of ``check-solution-citations``:

- **Diff-scoped by default**, skip rather than fall back without a base ref,
  blocking by default, and ``CEB_WHOLE_TREE=true`` to measure a corpus.
- **Headings break adjacency.** A heading between the solution and the result
  means the pair is not just before the result.

Configuration (environment variables, set by the composite action):
  CEB_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  CEB_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  CEB_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  CEB_FAIL          "false" => warning annotations only; default "true".
  CEB_WHOLE_TREE    "true" => check every result div, not only changed ones.
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
_DEFAULT_FAIL = True
ALLOW_MARKER = "check-exercise-before-result: allow"
RESULT_KINDS = ("thm", "lem", "cor", "prp")

ADVICE = (
    "put an exercise that asks for the result, then its solution, just "
    "before the result div, or add <!-- check-exercise-before-result: allow "
    "--> to the first line of the result if no exercise can precede it"
)

INCLUDE_RE = re.compile(r"\{\{<\s*include\s+([^\s>]+)\s*>\}\}")
SLIDEBREAK_RE = re.compile(r"\{\{<\s*slidebreak\s*>\}\}")
KIND_FILE_RE = re.compile(r"^_?([a-z]+)[-_]")
DIV_ID_RE = re.compile(r"#([a-z]+)-[A-Za-z0-9_-]+")
FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
HEADING_RE = re.compile(r"^#{1,6}\s")


class Block(NamedTuple):
    kind: str
    path: str     # file holding the block's source
    line: int     # 1-based line of the block's first line in that file
    inline: bool  # True when the block is a div written in the chapter itself


class Finding(NamedTuple):
    path: str
    line: int
    kind: str


def _strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)


def blocks_of(path: str, root_dir: str, depth: int = 0) -> List[Block]:
    """Flatten ``path`` into blocks, expanding includes (depth-limited)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            raw = handle.read()
    except OSError:
        return []
    lines = _strip_comments(raw).split("\n")
    out: List[Block] = []
    fence: Optional[Tuple[str, int]] = None
    nest = 0
    for idx, text in enumerate(lines):
        m = FENCE_RE.match(text)
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] and not m.group(2).strip():
                fence = None
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        dm = DIV_RE.match(text)
        if dm:
            if dm.group(2):
                if nest == 0:
                    idm = DIV_ID_RE.search(dm.group(2))
                    out.append(Block(idm.group(1) if idm else "other", path, idx + 1, True))
                nest += 1
            elif nest:
                nest -= 1
            continue
        if nest:
            continue
        if HEADING_RE.match(text):
            out.append(Block("heading", path, idx + 1, True))
            continue
        for inc in INCLUDE_RE.finditer(text):
            target = inc.group(1)
            base = os.path.basename(target)
            km = KIND_FILE_RE.match(base)
            kind = km.group(1) if km else "other"
            target_path = os.path.normpath(os.path.join(os.path.dirname(path), target))
            if not os.path.exists(target_path):
                target_path = os.path.normpath(os.path.join(root_dir, target))
            if kind in RESULT_KINDS + ("exr", "sol") or not os.path.exists(target_path) or depth >= 3:
                out.append(Block(kind, target_path, 1, False))
            else:
                out.extend(blocks_of(target_path, root_dir, depth + 1))
    return out


def unpaired_results(blocks: List[Block], lines_of) -> List[Block]:
    """Result blocks not directly preceded by an exercise and then a solution."""
    bad = []
    for i, blk in enumerate(blocks):
        if blk.kind not in RESULT_KINDS:
            continue
        first = lines_of(blk.path)
        if first is not None and ALLOW_MARKER in "\n".join(first[blk.line - 1:blk.line + 1]):
            continue
        if i >= 2 and blocks[i - 1].kind == "sol" and blocks[i - 2].kind == "exr":
            continue
        bad.append(blk)
    return bad


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
    findings: List[Finding]
    files: int
    skipped: bool


_CACHE: Dict[str, Optional[List[str]]] = {}


def _lines_of(path: str) -> Optional[List[str]]:
    if path not in _CACHE:
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                _CACHE[path] = handle.read().split("\n")
        except OSError:
            _CACHE[path] = None
    return _CACHE[path]


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    """Check results in changed files since ``base_ref``, or all when whole-tree."""
    out = _run_git(["ls-files", "--", *globs])
    if out is None:
        return Report([], 0, True)
    tracked = [r for r in out.splitlines() if r and not _ignored(r, ignores)]
    changed: Optional[Set[str]] = None
    if not whole_tree:
        if not base_ref:
            return Report([], 0, True)
        base = _run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, True)
        diff = _run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                         base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, True)
        added, _deleted = parse_diff(diff)
        changed = {os.path.normpath(p) for p, nums in added.items() if nums}

    findings: List[Finding] = []
    seen: Set[Tuple[str, int]] = set()
    chapters = [p for p in tracked if not os.path.basename(p).startswith("_")]
    for chapter in chapters:
        blocks = blocks_of(chapter, os.path.dirname(chapter) or ".")
        for blk in unpaired_results(blocks, _lines_of):
            key = (os.path.normpath(blk.path), blk.line)
            if key in seen:
                continue
            if changed is not None and os.path.normpath(blk.path) not in changed:
                continue
            seen.add(key)
            findings.append(Finding(os.path.normpath(blk.path), blk.line, blk.kind))
    return Report(findings, len(chapters), False)


def main() -> int:
    base_ref = os.environ.get("CEB_BASE_REF", "").strip()
    globs = os.environ.get("CEB_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("CEB_PATHS_IGNORE", "")))
    fail = _env_flag("CEB_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("CEB_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the exercise-before-result check for this run "
              f"({reason}; not falling back to a whole-tree scan, which would "
              f"reflag every result the corpus already carries).")
        return 0

    scope = "whole tree" if whole_tree else f"files changed since {base_ref}"
    print(f"Examined {report.files} chapter(s) (scope: {scope}).")
    severity = "error" if fail else "warning"
    for finding in report.findings:
        print(f"::{severity} file={finding.path},line={finding.line}::A result div "
              f"(#{finding.kind}-) is not preceded by an exercise and its solution. "
              f"Fix: {ADVICE}")
    if not report.findings:
        print("Every changed result div follows an exercise and its solution.")
        return 0
    print(f"\n{len(report.findings)} result div(s) without a preceding exercise-solution pair.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
