#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag an analysis choice in code that the prose around it never explains.

The lab's rule (Ezra, 2026-11-03; Morrison-Lab/ai-config#4905): every time an
author makes an arbitrary analysis choice, such as binning a variable, the
prose explains the decision in detail. Example: lds `fig-logistic-regression`
cut age into three-year bins and said nothing about why (lds#1725).

Whether an explanation is good is a judgment no script can make. This check is
a prompt: it flags a code line that makes a recognized choice (``cut()``,
``breaks =``, ``bins =``, ``set.seed()``, a bandwidth, a train/test split) in a
unit of the page whose prose holds no reason word.

The unit is the outermost div around the code (a figure, example or exercise),
or, outside any div, the text from the previous heading to the next one.

What is not flagged:

- a unit whose prose, outside code fences, display math and HTML comments,
  holds a reason word (``because``, ``chose``, ``choice``, ``compromise``,
  ``rather than``, ``alternative``, ``arbitrary``, ...);
- a code line starting with ``#`` (a comment or a ``#|`` chunk option);
- a line carrying ``<!-- check-unexplained-choices: allow -->``.

The pattern list is noisy by design (``seed = 1`` in a plain simulation is
fine), which is why the check is warn-only by default.

Design notes, in the model of ``check-unexplained-contrasts``:

- **Diff-scoped by default.** Only an added line is reported. The whole file
  is parsed, since the explaining prose may sit far from the changed line.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``UAC_WHOLE_TREE=true`` scans the
  whole tree, which measures how many existing choices go unexplained.
- **Warn-only by default** (``UAC_FAIL`` defaults to false).

Configuration (environment variables, set by the composite action):
  UAC_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  UAC_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  UAC_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  UAC_FAIL          "true" => error annotations and a failing exit;
                    default "false".
  UAC_WHOLE_TREE    "true" => scan every tracked matching file in full.
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
ALLOW_MARKER = "check-unexplained-choices: allow"

ADVICE = (
    "explain the choice in the prose next to it: what was chosen, what the "
    "alternatives were, and why this one, with numbers from the data where "
    "they bear on it; remove the choice if there is no reason; or add "
    "<!-- check-unexplained-choices: allow --> if it is not an analysis choice"
)

CHOICE_RE = re.compile(
    r"(\bcut\s*\("
    r"|\bcut_(?:number|interval|width)\s*\("
    r"|\bpd\.(?:cut|qcut)\s*\("
    r"|\bnp\.histogram\s*\("
    r"|\b(?:breaks|bins|binwidth|nbins|n_bins)\s*="
    r"|\bset\.seed\s*\(|\brandom_state\s*=|\bnp\.random\.seed\s*\("
    r"|\b(?:bw|bandwidth|span|threshold|cutoff)\s*=\s*[-0-9.]"
    r"|\b(?:train_test_split|initial_split)\s*\("
    r"|\btest_size\s*=|\bprop\s*=\s*[0-9.])"
)
REASON_RE = re.compile(
    r"\b(?:because|chose|chosen|choice|choose|so that|compromise|rather than|"
    r"trade-?off|in order to|why|reason|arbitrary|alternatives?|picked|"
    r"reproducib\w+|steady|noisy|stable)\b",
    re.IGNORECASE,
)

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
HEADING_RE = re.compile(r"^#{1,6}\s")
CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")


class Finding(NamedTuple):
    line: int
    phrase: str


class _Unit:
    """The text a choice is read against: its hits and whether prose explains."""

    def __init__(self) -> None:
        self.hits: List[Finding] = []
        self.explained = False

    def flush(self) -> List[Finding]:
        found = [] if self.explained else self.hits
        self.hits, self.explained = [], False
        return found


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


def scan_choices(lines: List[str]) -> List[Finding]:
    """Choices in code whose unit (outer div, or section) has no reason prose."""
    findings: List[Finding] = []
    section = _Unit()
    depth = 0
    outer = _Unit()
    fence: Optional[Tuple[str, int]] = None
    in_math = in_comment = False
    for idx, original in enumerate(lines):
        raw = original
        if fence is None:
            raw, in_comment = strip_comment(raw, in_comment)
        unit = outer if depth > 0 else section
        m = FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
                continue
            code = raw.strip()
            if code and not code.startswith("#") and ALLOW_MARKER not in original:
                hit = CHOICE_RE.search(code)
                if hit:
                    unit.hits.append(Finding(idx + 1, hit.group(1).strip("( =")))
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
                if depth == 0:
                    findings.extend(section.flush())
                depth += 1
            elif depth > 0:
                depth -= 1
                if depth == 0:
                    findings.extend(outer.flush())
            continue
        if depth == 0 and HEADING_RE.match(raw):
            findings.extend(section.flush())
            continue
        if REASON_RE.search(CODE_SPAN_RE.sub(" ", raw)):
            unit.explained = True
    findings.extend(outer.flush())
    findings.extend(section.flush())
    return sorted(findings)


def format_message(phrase: str) -> str:
    return (f"Analysis choice (`{phrase}`) with no reason in the prose of its "
            f"figure, example or section. Fix: {ADVICE}")


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
        for found in scan_choices(content):
            if keep is None or found.line in keep:
                findings.append((rel, found))
    return Report(findings, files, False)


def main() -> int:
    base_ref = os.environ.get("UAC_BASE_REF", "").strip()
    globs = os.environ.get("UAC_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("UAC_PATHS_IGNORE", "")))
    fail = _env_flag("UAC_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("UAC_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the unexplained-choices check for this run "
              f"({reason}; not falling back to a whole-tree scan, which would "
              f"reflag every choice the corpus already carries).")
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.files} file(s) (scope: {scope}).")
    severity = "error" if fail else "warning"
    for rel, found in report.findings:
        print(f"::{severity} file={rel},line={found.line}::{format_message(found.phrase)}")
    if not report.findings:
        print("No unexplained analysis choice found.")
        return 0
    print(f"\n{len(report.findings)} unexplained analysis choice(s).")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
