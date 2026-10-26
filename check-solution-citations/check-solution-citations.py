#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a citation of a solution inside a proof or result div.

The lab's rule (Ezra, 2026-10-26; Morrison-Lab/gha#1234): a derivation never
cites a solution to an exercise. A solution that a later argument relies on is
followed by a result div (``#thm-``, ``#lem-``, ``#cor-`` or ``#prp-``), and the
later argument cites that result div. The one exception is an exercise that
asks students to prove a result before the result is stated: the result's proof
may cite the solution that precedes it.

What is flagged: a cross-reference ``@sol-...`` on a line inside a ``proof`` div
or a ``#thm-``/``#lem-``/``#cor-``/``#prp-`` div, including any div nested in
one. The finding sits on the line that holds the reference.

What is not counted, to avoid false positives:

- lines inside code fences, display math (``$$``), HTML comments or inline code;
- a line carrying ``<!-- check-solution-citations: allow -->``, the explicit
  mark for the exception above (the exercise asks for this proof);
- a line that says "the solution to @exr-slug" or "the answer to @exr-slug", the lab's existing
  wording for a result whose exercise asks for the proof; it excuses only
  ``@sol-slug``, the solution that shares the exercise's slug;
- a ``@sol-`` reference outside a proof or result div, such as in another
  solution, where solutions build on one another.

Design notes, in the model of ``check-def-commentary``:

- **Diff-scoped by default.** Only an added line is reported. The whole file
  is parsed, since the div opens far above the line that changed. An added
  line whose exact text was also deleted in the diff counts as moved.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``CSC_WHOLE_TREE=true`` scans the
  whole tree, which measures how many existing proofs cite a solution.
- **Blocking by default** (``CSC_FAIL`` defaults to true): it is diff-scoped,
  so it reflags nothing the corpus already carries.

Configuration (environment variables, set by the composite action):
  CSC_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  CSC_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  CSC_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  CSC_FAIL          "false" => warning annotations only; default "true".
  CSC_WHOLE_TREE    "true" => scan every tracked matching file in full.
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
ALLOW_MARKER = "check-solution-citations: allow"

ADVICE = (
    "follow the solution with a result div (#thm-, #lem-, #cor- or #prp-) "
    "and cite that instead; if the exercise asks students to prove this "
    "result, add <!-- check-solution-citations: allow --> to the line"
)

SOL_REF_RE = re.compile(r"(?<![A-Za-z0-9._-])@sol-[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*")
# "This is the solution (or answer) to @exr-x: see @sol-x" marks the exception,
# and only for the solution that shares the exercise's slug.
EXCEPTION_RE = re.compile(
    r"(?:solution|answer)s?\s+to\s+(?:Exercise\s+)?\[?-?@exr-([A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*)",
    re.IGNORECASE)

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
# Match the div's own class or id token, never text inside a quoted attribute.
SCOPE_RE = re.compile(r"(?:^|[\s{])(?:\.?proof|#(?:thm|lem|cor|prp)-[A-Za-z0-9_-]*)(?=[\s}.#]|$)")
PROOF_RE = re.compile(r"(?:^|[\s{])\.?proof(?=[\s}.#]|$)")
QUOTED_RE = re.compile(r'"[^"]*"|\'[^\']*\'')
CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")


class Finding(NamedTuple):
    line: int
    ref: str


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


def scan_proofs(lines: List[str]) -> List[Finding]:
    """Solution references inside a proof or result div, nested divs included."""
    findings: List[Finding] = []
    # One entry per open div: [in scope, is a proof, content lines, structured].
    # A proof whose whole body is one line with one solution citation is a
    # pointer to the solution of the exercise that asks for the result: allowed.
    stack: List[list] = []
    several: Set[int] = set()  # 0-based lines citing more than one solution
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
            if stack:
                stack[-1][3] = True
            continue
        if raw.count("$$") % 2 == 1:
            in_math = not in_math
            if stack:
                stack[-1][3] = True
            continue
        if in_math:
            continue
        dm = DIV_RE.match(raw)
        if dm:
            if dm.group(2):
                attrs = QUOTED_RE.sub('', dm.group(2))
                if stack:
                    stack[-1][3] = True
                stack.append([bool(SCOPE_RE.search(attrs)),
                              bool(PROOF_RE.search(attrs)), [], False])
            elif stack:
                _, is_proof, body, structured = stack.pop()
                if (is_proof and not structured and len(body) == 1
                        and body[0] not in several):
                    findings = [f for f in findings if f.line != body[0] + 1]
            continue
        if stack and raw.strip():
            stack[-1][2].append(idx)
        if not any(entry[0] for entry in stack) or ALLOW_MARKER in original:
            continue
        prose = CODE_SPAN_RE.sub(" ", raw)
        excused = {m.group(1) for m in EXCEPTION_RE.finditer(prose)}
        if len(SOL_REF_RE.findall(prose)) > 1:
            several.add(idx)
        for hit in SOL_REF_RE.finditer(prose):
            if hit.group(0)[len("@sol-"):] not in excused:
                findings.append(Finding(idx + 1, hit.group(0)))
                break
    return findings


def format_message(ref: str) -> str:
    return (f"A proof or result div cites the solution {ref}; a derivation "
            f"cites a result div, not a solution. Fix: {ADVICE}")


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
        for found in scan_proofs(content):
            if keep is None or found.line in keep:
                findings.append((rel, found))
    return Report(findings, files, False)


def main() -> int:
    base_ref = os.environ.get("CSC_BASE_REF", "").strip()
    globs = os.environ.get("CSC_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("CSC_PATHS_IGNORE", "")))
    fail = _env_flag("CSC_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("CSC_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the solution-citations check for this run "
              f"({reason}; not falling back to a whole-tree scan, which would "
              f"reflag every proof the corpus already carries).")
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.files} file(s) (scope: {scope}).")
    severity = "error" if fail else "warning"
    for rel, found in report.findings:
        print(f"::{severity} file={rel},line={found.line}::{format_message(found.ref)}")
    if not report.findings:
        print("No proof or result div cites a solution.")
        return 0
    print(f"\n{len(report.findings)} solution citation(s) inside proof or result divs.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
