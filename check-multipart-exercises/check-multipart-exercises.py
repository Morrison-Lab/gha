#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag an exercise div that asks more than one thing.

The lab's rule (Ezra, 2026-10-22; Morrison-Lab/gha#1156): split every
multi-part exercise into separate ``#exr-`` divs, each with its own solution.

What is flagged: a fenced div whose id starts with ``exr-`` and whose body
holds either

- two or more list items in the same marker style, such as ``(a)``/``(b)``,
  ``a.``/``b.``, ``(i)``/``(ii)``, ``1.``/``2.`` or ``1)``/``2)``, bare or
  bolded, or
- inline parts in running text, such as "(a) ... (b) ...".

The finding sits on the line of the second part. A div is checked when the
diff adds at least one line inside it, so a one-line fix to an old
multi-part exercise is reported too (the exercise is revised, so split it).

What is not counted:

- text inside a code fence, an HTML comment, a display-math block or inline
  math (``(a)`` in a formula is not a part);
- a div nested inside the exercise is read as part of the exercise;
- bullet lists (``-``, ``*``, ``+``): "Let:" and "Assume:" lists are bullets;
- an exercise that carries the comment ``<!-- multipart-ok: <reason> -->``
  (for example the options of a single-choice question).

Design notes, in the model of ``check-one-div-per-subfile``:

- **Diff-scoped by default.** Only an exercise with a line *added* since
  ``MPE_BASE_REF`` is reported; the whole div is parsed. An added line whose
  exact text was also deleted in the same diff is moved, and a blank line is
  not content.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed (a shallow clone), the check skips with a warning.
  ``MPE_WHOLE_TREE=true`` asks for the whole tree, which measures the corpus.
- **Blocking by default** (``MPE_FAIL`` defaults to true): the rule is
  settled, and the diff scope keeps old exercises from being reflagged.

Configuration (environment variables, set by the composite action):
  MPE_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  MPE_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  MPE_PATHS_IGNORE  Comma/newline-separated glob patterns to skip. Supports
                    ``*``, ``?`` and recursive ``**``.
  MPE_FAIL          "false" => warning annotations only; default "true".
  MPE_WHOLE_TREE    "true" => scan every tracked matching file in full.
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

ADVICE = (
    "give each part its own exercise div (and its own solution), "
    "in its own subfile, and include each from the chapter"
)

# -- Parsing -----------------------------------------------------------------

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
EXR_ID_RE = re.compile(r"#exr-")
ALLOW_RE = re.compile(r"<!--\s*multipart-ok\b", re.IGNORECASE)
CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")
INLINE_MATH_RE = re.compile(r"(?<!\\)\$[^$\n]+?(?<!\\)\$")

_EMPH = r"(?:\*\*|__|\*|_)?"
_LABEL = r"(?:[A-Za-z]|[ivxlcdmIVXLCDM]{2,}|\d{1,2})"
# Outside parentheses only a lowercase letter or a number marks a part, so
# "I. Newton" and "mild." at a line start are prose.
_BARE_LABEL = r"(?:[a-z]|\d{1,2})"
# A part marker opening a line: "(a) ", "a. ", "a) ", "1. ", bare or bolded.
MARKER_RE = re.compile(
    r"^[ \t]*(?:>\s*)*" + _EMPH
    + r"(?:\((?P<paren>" + _LABEL + r")\)|(?P<dot>" + _BARE_LABEL + r")(?P<end>[.)]))"
    + _EMPH + r"(?:\s+|$)\S?"
)
# Running text: "(a) ... (b)", "(i) ... (ii)", "(1) ... (2)" on one passage.
INLINE_PAIRS = (("a", "b"), ("A", "B"), ("i", "ii"), ("I", "II"), ("1", "2"))


class Part(NamedTuple):
    line: int
    style: str


class Exercise(NamedTuple):
    start: int  # line of the opening fence
    end: int  # line of the closing fence (or the last line)
    attrs: str


def strip_comments(raw: str, in_comment: bool) -> Tuple[str, bool]:
    """Remove HTML comment text from one line; say whether one stays open."""
    if in_comment:
        end = raw.find("-->")
        if end < 0:
            return "", True
        raw = raw[end + 3:]
    spans: List[str] = []
    raw = CODE_SPAN_RE.sub(lambda m: spans.append(m.group(0)) or "\0", raw)
    while True:
        start = raw.find("<!--")
        end = raw.find("-->", start + 4) if start >= 0 else -1
        if end < 0:
            break
        raw = raw[:start] + raw[end + 3:]
    start = raw.find("<!--")
    opened = start >= 0
    if opened:
        raw = raw[:start]
    it = iter(spans)
    return re.sub("\0", lambda _: next(it), raw), opened


def find_exercises(lines: List[str]) -> List[Exercise]:
    """Outermost ``exr-`` divs outside code fences and HTML comments."""
    fence: Optional[Tuple[str, int]] = None
    depth = 0
    in_comment = False
    open_ex: Optional[Tuple[int, str, int]] = None  # line, attrs, depth at open
    found: List[Exercise] = []
    for idx, raw in enumerate(lines):
        if fence is None:
            raw, in_comment = strip_comments(raw, in_comment)
        m = FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        dm = DIV_RE.match(raw)
        if not dm:
            continue
        attrs = dm.group(2)
        if attrs:
            if open_ex is None and EXR_ID_RE.search(attrs):
                open_ex = (idx + 1, attrs, depth)
            depth += 1
        elif depth > 0:
            depth -= 1
            if open_ex is not None and depth == open_ex[2]:
                found.append(Exercise(open_ex[0], idx + 1, open_ex[1]))
                open_ex = None
    if open_ex is not None:
        found.append(Exercise(open_ex[0], len(lines) + 1, open_ex[1]))
    return found


def marker_style(raw: str) -> Optional[str]:
    """The part-marker style a line opens with, or None."""
    m = MARKER_RE.match(raw)
    if not m:
        return None
    if m.group("paren") is not None:
        label, shape = m.group("paren"), "paren"
    else:
        label, shape = m.group("dot"), "dot" + m.group("end")
    kind = "num" if label.isdigit() else "alpha"
    return f"{shape}-{kind}"


def body_text(lines: List[str]) -> List[Tuple[int, str]]:
    """Prose lines of an exercise body: not code, not display math, no
    comments, and with inline math and code spans blanked out."""
    out: List[Tuple[int, str]] = []
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    in_math = False
    for idx, raw in enumerate(lines):
        if fence is None:
            raw, in_comment = strip_comments(raw, in_comment)
        m = FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        if raw.count("$$") % 2:
            in_math = not in_math
            continue
        if in_math or "$$" in raw:
            continue
        text = INLINE_MATH_RE.sub(" ", CODE_SPAN_RE.sub(" ", raw))
        out.append((idx + 1, text))
    return out


def find_parts(lines: List[str], ex: Exercise) -> List[Part]:
    """Second and later parts of one exercise, empty when it has one part."""
    body = lines[ex.start:max(ex.end - 1, ex.start)]
    if any(ALLOW_RE.search(line) for line in body):
        return []
    prose = [(n + ex.start, t) for n, t in body_text(body)]
    seen: Dict[str, List[int]] = {}
    for n, text in prose:
        style = marker_style(text)
        if style:
            seen.setdefault(style, []).append(n)
    extra = [Part(ns[1], style) for style, ns in seen.items() if len(ns) > 1]
    if extra:
        return sorted(extra)
    joined = " ".join(t for _, t in prose)
    for first, second in INLINE_PAIRS:
        a = re.search(r"(?<![\w(])\(" + re.escape(first) + r"\)", joined)
        b = re.search(r"(?<![\w(])\(" + re.escape(second) + r"\)", joined)
        if a and b and a.start() < b.start():
            for n, text in prose:
                if re.search(r"\(" + re.escape(second) + r"\)", text):
                    return [Part(n, "inline")]
    return []


def scan_file(lines: List[str]) -> Tuple[List[Tuple[Exercise, Part]], int]:
    """Multi-part findings as (exercise, first extra part), and exercises seen."""
    exercises = find_exercises(lines)
    findings = []
    for ex in exercises:
        parts = find_parts(lines, ex)
        if parts:
            findings.append((ex, parts[0]))
    return findings, len(exercises)


# -- Messages ----------------------------------------------------------------

def format_message(style: str) -> str:
    what = ("parts written inline, such as (a) ... (b)" if style == "inline"
            else "a second list item in the same part style")
    return (f"This exercise holds more than one part ({what}); split every "
            f"multi-part exercise into separate divs. Fix: {ADVICE}. "
            f"For a single-choice question, add <!-- multipart-ok: reason -->")


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
    findings: List[Tuple[str, int, str]]  # (path, line of the 2nd part, style)
    files: int
    exercises: int
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
    """Scan exercises with an added line since ``base_ref``, or all when whole-tree."""
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

    findings: List[Tuple[str, int, str]] = []
    files = exercises = 0
    for rel in sorted(wanted):
        content = _read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        found, seen = scan_file(content)
        exercises += seen
        for ex, part in found:
            touched = keep is None or any(ex.start <= n <= ex.end for n in keep)
            if touched:
                findings.append((rel, part.line, part.style))
    return Report(findings, files, exercises, False)


def main() -> int:
    base_ref = os.environ.get("MPE_BASE_REF", "").strip()
    globs = os.environ.get("MPE_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("MPE_PATHS_IGNORE", "")))
    fail = _env_flag("MPE_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("MPE_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the multi-part exercise check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every exercise the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.exercises} exercise div(s) across {report.files} "
        f"file(s) (scope: {scope})."
    )
    severity = "error" if fail else "warning"
    for rel, line, style in report.findings:
        print(f"::{severity} file={rel},line={line}::{format_message(style)}")
    if not report.findings:
        print("No touched exercise holds more than one part.")
        return 0
    print(f"\n{len(report.findings)} exercise(s) hold more than one part.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
