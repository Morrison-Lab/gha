#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag words and phrases that a style source advises against, in prose.

Three rules, each with a source that was read (psw#418):

- **position words**: ``above`` or ``below`` used for a place in the
  document, such as "the table above" or "as shown below". Refer to the
  result by its label instead. Source: Google developer documentation style
  guide, word list, entries "above" and "below" ("Don't use to refer to a
  position in a document").
- **effort words**: ``just``, ``easy``, ``easily``. Source: the same word
  list ("just": "Avoid. Usually, just is a filler word that you can delete
  without affecting your meaning"; "easy, easily": "Try eliminating this
  word").
- **time-relative words**: ``currently``, ``recently``, ``nowadays``, ``at
  present``, ``at the moment``, ``these days``. Source: Google, "Timeless
  documentation" ("Words like now, new, and currently can render such
  documentation inaccurate, outdated, or unmeaningful"). ``now`` and ``new``
  are not flagged because "now" and the term "new observation" are common
  correct uses a regex cannot tell apart; review covers them. ``recently`` is
  psw's own extension, which the guide does not list.

What is flagged is deliberately narrow. ``above`` and ``below`` are flagged
only in the position senses (after a document noun, after "as shown/noted/..."
or at the end of a clause); "above the threshold" passes. ``just`` is not
flagged before ``before``, ``after``, ``as``, ``like``, ``then``, ``enough``,
``in time``, ``once`` or ``now``.

Skipped: code fences and spans, HTML comments, YAML front matter, and a line
carrying, or following, ``<!-- check-avoided-words: allow -->``.

Design notes, in the model of ``check-avoided-words``, whose diff model and
Markdown masking are copied here rather than imported:

- **Diff-scoped by default.** Only lines *added* since ``CAW_BASE_REF`` are
  reported. An added line whose exact text was also deleted in the same diff
  is treated as moved. ``CAW_WHOLE_TREE=true`` scans everything.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning instead of scanning the whole tree.
- **Warn-only by default** (``CAW_FAIL`` defaults to false).
- **The search space is reported.** Every run prints how many files and lines
  it examined.

Configuration (environment variables, set by the composite action):
  CAW_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  CAW_GLOBS         Space-separated git pathspecs.
  CAW_PATHS_IGNORE  Comma/newline-separated glob patterns to skip (``*``,
                    ``?`` and recursive ``**``).
  CAW_FAIL          "true" => exit 1 on a finding.
  CAW_WHOLE_TREE    "true" => scan every tracked matching file in full.
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

DEFAULT_GLOBS = "*.qmd *.md"
_DEFAULT_FAIL = False

POSITION_NOUNS = (
    "equation|formula|figure|table|result|theorem|lemma|corollary|definition|"
    "example|exercise|section|derivation|code|text|list|plot|chart|"
    "expression|model|step|line|paragraph|argument|proof|solution|passage|"
    "display|inequality|identity|chunk|output|remark|proposition"
)
ASAS = (
    "shown|noted|stated|discussed|described|seen|mentioned|derived|defined|"
    "proved|explained|computed|given|illustrated|see"
)
POSITION_RE = re.compile(
    r"(?i)\b(?:the|this|that|these|those)\s+(?:\w+\s+)?(?:" + POSITION_NOUNS
    + r")s?\s+(above|below)\b"
    r"|\b(?:" + ASAS + r")\s+(above|below)\b"
    r"|,\s*(above|below)\s*[.,;:)]"
)
EFFORT_RE = re.compile(
    r"(?i)\b(?:just(?!\s+(?:before|after|as|like|then|enough|in\s+time|once|"
    r"now)\b)|easy|easily)\b"
)
TIME_RE = re.compile(
    r"(?i)\b(?:currently|recently|nowadays|at\s+present|at\s+the\s+moment|"
    r"these\s+days)\b"
)
RULES = (
    ("position", POSITION_RE,
     'Refer to a place in the document by its label, not "above" or "below"; '
     "the same source renders in several formats (psw#418; Google style guide, "
     'word list, entries "above" and "below").'),
    ("effort", EFFORT_RE,
     'Delete "just", "easy" and "easily" unless they carry meaning; they '
     "judge difficulty or add nothing (psw#418; Google style guide, word list)."),
    ("time", TIME_RE,
     "Give a date or a version instead of a time-relative word; it goes stale "
     "(psw#418; Google style guide, Timeless documentation)."),
)

FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*(\S*)")
ALLOW_RE = re.compile(r"<!--\s*check-avoided-words:\s*allow\s*-->")
CODE_SPAN_RE = re.compile(r"(`+).+?\1")

class Finding(NamedTuple):
    line: int
    rule: str
    phrase: str


def _blank_closed_comments(line: str) -> str:
    """Blank each ``<!-- ... -->`` that opens and closes on this line.

    A scan with ``find`` rather than a regex: the comment-open state is
    carried across lines by the caller, so a one-line pattern is the wrong
    tool for an HTML comment, and CodeQL flags it as such.
    """
    out = line
    pos = 0
    while True:
        start = out.find("<!--", pos)
        if start < 0:
            return out
        end = out.find("-->", start + 4)
        if end < 0:
            return out
        out = out[:start] + " " * (end + 3 - start) + out[end + 3:]
        pos = end + 3


def _mask_markdown_line(line: str, in_comment: bool) -> Tuple[str, bool]:
    """Blank code spans and HTML comments; track a comment open across lines."""
    out = line
    if in_comment:
        end = out.find("-->")
        if end < 0:
            return "", True
        out, in_comment = " " * (end + 3) + out[end + 3:], False
    out = _blank_closed_comments(out)
    start = out.find("<!--")
    if start >= 0:
        out, in_comment = out[:start], True
    out = CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), out)
    return out, in_comment


def scan_file(lines: List[str]) -> Tuple[List[Finding], int]:
    """``([Finding, ...], lines examined)`` for a Markdown-family file."""
    found: List[Finding] = []
    examined = 0
    fence: Optional[Tuple[str, int]] = None  # (marker, length)
    in_comment = False
    in_front = bool(lines) and lines[0].strip() == "---"
    for number, raw in enumerate(lines, 1):
        examined += 1
        if in_front:
            if number > 1 and raw.strip() in ("---", "..."):
                in_front = False
            continue
        m = FENCE_RE.match(raw)
        if fence is None and m and not in_comment:
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                    and not m.group(2):
                fence = None
            continue
        masked, in_comment = _mask_markdown_line(raw, in_comment)
        allowed = ALLOW_RE.search(raw) or (
            number > 1 and ALLOW_RE.search(lines[number - 2]))
        if allowed:
            continue
        for rule, pattern, _message in RULES:
            hit = pattern.search(masked)
            if hit:
                found.append(Finding(number, rule, hit.group(0).strip()))
    return found, examined


def format_message(finding: Finding) -> str:
    message = dict((r, m) for r, _p, m in RULES)[finding.rule]
    return f'"{finding.phrase}": {message}'


def _run_git(args: List[str]) -> Optional[str]:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    return res.stdout if res.returncode == 0 else None


_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_diff(diff: str) -> Tuple[Dict[str, Dict[int, str]], Set[str]]:
    """Added ``{path: {line_number: text}}`` and the set of deleted texts.

    Hunk header counts decide where a hunk ends, so an added line that begins
    with two plus signs is never mistaken for a ``+++`` file header.
    """
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


def compile_globs(patterns: List[str]) -> List["re.Pattern[str]"]:
    compiled = []
    for pat in patterns:
        compiled.append(_glob_to_regex(pat))
        if "*" not in pat and "?" not in pat:
            compiled.append(_glob_to_regex(pat.rstrip("/") + "/**"))
    return compiled


def _matches(rel: str, globs: List["re.Pattern[str]"]) -> bool:
    return any(r.match(rel) for r in globs)


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
    lines: int
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
    """Scan the added lines since ``base_ref``, or every line when whole-tree."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = _run_git(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, 0, True)
        for rel in out.splitlines():
            if rel and not _matches(rel, ignores):
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
            if _matches(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if not (text.strip() and text in deleted)}

    findings: List[Tuple[str, Finding]] = []
    files = lines = 0
    for rel in sorted(wanted):
        content = _read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        for finding in scan_file(content)[0]:
            if keep is None or finding.line in keep:
                findings.append((rel, finding))
    return Report(findings, files, lines, False)


def main() -> int:
    base_ref = os.environ.get("CAW_BASE_REF", "").strip()
    globs = os.environ.get("CAW_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_globs(_split_list(os.environ.get("CAW_PATHS_IGNORE", "")))
    fail = _env_flag("CAW_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("CAW_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        # With no base-ref (a push run) the skip is expected, so it is not an annotation.
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the avoided-words check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every use the repository already has)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.lines} line(s) across {report.files} file(s) "
          f"(scope: {scope}).")
    if not report.findings:
        print('No position, effort or time-relative word found.')
        return 0

    severity = "error" if fail else "warning"
    for rel, finding in report.findings:
        print(f"::{severity} file={rel},line={finding.line}::"
              f"{format_message(finding)}")
    print(f"\n{len(report.findings)} line(s) use a word a style source advises against.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
