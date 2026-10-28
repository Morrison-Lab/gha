#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag an exercise part that asks for more than one thing.

The lab's rule (Ezra, 2026-10-27, review of Morrison-Lab/mds#498): each
exercise part asks for one thing, and a part that asks for several is split
into several parts, with the solution split the same way. "Compute the
slope exactly, and compare it with the fitted value" is two asks.

What is a part: a list item (bullet, numbered, lettered) or a paragraph in
the body of a fenced div whose id starts with ``exr-``, outside any nested
``.sol`` or ``.solution`` div.

What is an ask: a clause that opens with an imperative verb the exercises
use (Compute, Find, Show, Compare, Plot, Explain, ...). A part is flagged
when it holds two or more asks: two such sentences, or one sentence whose
clauses after ", and", ", then", ";", "and then", "and also", or a bare
"and" before such a verb open with such a verb. The finding sits on the first
line of the part.

This is a heuristic, so it warns by default (``SAP_FAIL=true`` blocks).

What is not counted:

- text inside a code fence, an HTML comment, display math or inline math;
- a part that carries ``<!-- single-ask-ok: <reason> -->`` on its first line
  or the line before it, or an exercise that carries it on its opening
  fence or the line before that.

Design notes, in the model of ``check-multipart-exercises``:

- **Diff-scoped by default.** A part is reported when the diff adds a line
  inside it, so an old part the PR does not touch is never reflagged.
- **Skip, not fall back.** With no base ref the check skips quietly; when the
  diff against a given base ref cannot be computed, it skips with a warning.
  ``SAP_WHOLE_TREE=true`` scans the whole tree to measure the corpus.

Configuration (environment variables, set by the composite action):
  SAP_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  SAP_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  SAP_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  SAP_FAIL          "true" => error annotations and a failing exit.
  SAP_WHOLE_TREE    "true" => scan every tracked matching file in full.
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

ADVICE = "give each ask its own part, and split the solution the same way"

# -- Parsing -----------------------------------------------------------------

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
EXR_ID_RE = re.compile(r"#exr-")
SOL_RE = re.compile(r"(?:^|[\s{])\.(?:sol|solution)\b")
ALLOW_RE = re.compile(r"<!--\s*single-ask-ok\b", re.IGNORECASE)
CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")
INLINE_MATH_RE = re.compile(r"(?<!\\)\$[^$\n]+?(?<!\\)\$")
ITEM_RE = re.compile(
    r"^[ \t]*(?:>\s*)*(?:[-*+]|\(?(?:[A-Za-z]|[ivxlcdm]{2,}|\d{1,3})[.)])\s+"
)

ASK_VERBS = (
    "calculate compute evaluate find determine derive show prove verify check "
    "compare contrast explain describe interpret justify argue state give list "
    "identify name write plot draw sketch graph fit estimate predict simulate "
    "implement run test solve simplify report summarize summarise classify "
    "decide discuss illustrate construct choose select apply use "
    "differentiate integrate minimize minimise maximize maximise expand "
    "rewrite repeat modify train tune conclude"
).split()
ASK_VERB = r"(?:" + "|".join(ASK_VERBS) + r")"
# A clause opening with an ask: "Compute ...", "First, compute ...", "then plot ...".
ASK_RE = re.compile(
    r"^\s*(?:(?:first|next|then|finally|also|now|lastly|second|third)\b,?\s+)*"
    + r"(?!write\s+for\b)"  # notation ("write $q$ for ..."), not an ask
    + ASK_VERB + r"\b",
    re.IGNORECASE,
)
# Joins between the clauses of one sentence.
CLAUSE_SPLIT_RE = re.compile(
    r",\s+and\s+|;\s+(?:and\s+)?|,\s+then\s+|\s+and\s+then\s+|\s+and\s+also\s+"
    r"|\s+and\s+(?=" + ASK_VERB + r"\b)",
    re.IGNORECASE,
)
DISPLAY_PAIR_RE = re.compile(r"\$\$.*?\$\$")
SENT_SPLIT_RE = re.compile(r"(?<=[.?!:])\s+(?=[A-Z])")


class Exercise(NamedTuple):
    start: int  # line of the opening fence
    end: int  # line of the closing fence (or the last line)
    attrs: str


class Part(NamedTuple):
    line: int  # first line of the part
    end: int  # last line of the part
    asks: int


def strip_comments(raw: str, in_comment: bool) -> Tuple[str, bool]:
    """Remove HTML comment text from one line; say whether one stays open."""
    if in_comment:
        end = raw.find("-->")
        if end < 0:
            return "", True
        raw = raw[end + 3:]
    spans: List[str] = []
    raw = CODE_SPAN_RE.sub(
        lambda m: spans.append(m.group(0)) or f"\0{len(spans) - 1}\0", raw)
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
    return re.sub("\0(\\d+)\0", lambda m: spans[int(m.group(1))], raw), opened


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
        # A $$...$$ pair on one line is inline display math: blank it and
        # keep the prose around it.
        plain = CODE_SPAN_RE.sub(" ", raw)
        if not in_math:
            plain = DISPLAY_PAIR_RE.sub(" ", plain)
        if "$$" in plain:
            # Pieces between the delimiters alternate display math and prose;
            # keep the prose, which is outside the math at either end.
            pieces = plain.split("$$")
            plain = " ".join(p for i, p in enumerate(pieces)
                             if (i % 2 == 0) != in_math)
            if len(pieces) % 2 == 0:
                in_math = not in_math
        elif in_math:
            continue
        text = INLINE_MATH_RE.sub(" ", plain)
        out.append((idx + 1, text))
    return out


def drop_solutions(body: List[str]) -> List[str]:
    """Blank the lines of nested ``.sol`` / ``.solution`` divs."""
    out: List[str] = []
    sol_depth: Optional[int] = None
    depth = 0
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    for raw in body:
        keep = sol_depth is None
        # A ``:::`` inside a code fence or an HTML comment is not a div.
        seen = raw
        if fence is None:
            seen, in_comment = strip_comments(raw, in_comment)
        fm = FENCE_RE.match(seen)
        dm = None
        if fence is not None:
            if (fm and fm.group(1)[0] == fence[0] and len(fm.group(1)) >= fence[1]
                    and not fm.group(2).strip()):
                fence = None
        elif fm and not (fm.group(1)[0] == "`" and "`" in fm.group(2)):
            fence = (fm.group(1)[0], len(fm.group(1)))
        else:
            dm = DIV_RE.match(seen)
        if dm:
            if dm.group(2):
                if sol_depth is None and SOL_RE.search(dm.group(2)):
                    sol_depth = depth
                    keep = False
                depth += 1
            elif depth > 0:
                depth -= 1
                if sol_depth is not None and depth == sol_depth:
                    sol_depth = None
                    keep = False
        out.append(raw if keep else "")
    return out


def count_asks(text: str) -> int:
    """Number of imperative asks in a part's prose."""
    asks = 0
    text = re.sub(r"\bcompare\s+and\s+contrast\b", "compare", text, flags=re.IGNORECASE)
    for sentence in SENT_SPLIT_RE.split(text):
        for clause in CLAUSE_SPLIT_RE.split(sentence):
            if ASK_RE.match(clause):
                asks += 1
    return asks


def find_parts(lines: List[str], ex: Exercise) -> List[Part]:
    """Parts of one exercise that hold two or more asks."""
    body = lines[ex.start:max(ex.end - 1, ex.start)]
    fence = lines[ex.start - 1]
    before_fence = lines[ex.start - 2] if ex.start >= 2 else ""
    if ALLOW_RE.search(fence) or ALLOW_RE.search(before_fence):
        return []
    units: List[List[object]] = []  # [first line, last line, [chunks]]
    previous = 0
    kept = drop_solutions(body)  # solution lines are blank, so they end a part
    in_comment = False
    for i, raw in enumerate(kept):
        # A line holding only an HTML comment ends a part, as a blank line does.
        bare, in_comment = strip_comments(raw, in_comment)
        if raw.strip() and not bare.strip():
            kept[i] = ""

    def filled(k: int) -> bool:
        return bool(kept[k - ex.start - 1].strip())

    for n, text in body_text(kept):
        n += ex.start
        if DIV_RE.match(text):
            previous = 0
            continue
        if not text.strip() and not filled(n):
            continue
        if ITEM_RE.match(text):
            units.append([n, n, [ITEM_RE.sub("", text, count=1)]])
        elif previous and units and all(filled(k) for k in range(previous + 1, n)):
            units[-1][1] = n
            units[-1][2].append(text.strip())  # type: ignore[union-attr]
        else:
            units.append([n, n, [text.strip()]])
        previous = n
    found: List[Part] = []
    for first, last, chunks in units:
        asks = count_asks(" ".join(chunks))  # type: ignore[arg-type]
        before = lines[first - 2] if first >= 2 else ""
        if asks >= 2 and not ALLOW_RE.search(before) and not ALLOW_RE.search(lines[first - 1]):
            found.append(Part(first, last, asks))  # type: ignore[arg-type]
    return found


def scan_file(lines: List[str]) -> Tuple[List[Part], int]:
    """Parts that ask more than once, and the number of exercises seen."""
    exercises = find_exercises(lines)
    findings: List[Part] = []
    for ex in exercises:
        findings.extend(find_parts(lines, ex))
    return findings, len(exercises)


# -- Messages ----------------------------------------------------------------

def format_message(asks: int) -> str:
    return (f"This exercise part asks for {asks} things; each part asks for one "
            f"(Ezra, 2026-10-27). Fix: {ADVICE}. "
            f"For a single compound ask, add <!-- single-ask-ok: reason -->")


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
    findings: List[Tuple[str, int, int]]  # (path, first line of the part, asks)
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

    findings: List[Tuple[str, int, int]] = []
    files = exercises = 0
    for rel in sorted(wanted):
        content = _read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        found, seen = scan_file(content)
        exercises += seen
        for part in found:
            if keep is None or any(part.line <= n <= part.end for n in keep):
                findings.append((rel, part.line, part.asks))
    return Report(findings, files, exercises, False)


def main() -> int:
    base_ref = os.environ.get("SAP_BASE_REF", "").strip()
    globs = os.environ.get("SAP_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("SAP_PATHS_IGNORE", "")))
    fail = _env_flag("SAP_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("SAP_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        if whole_tree:
            print("::warning::Skipping the single-ask part check for this run "
                  "(could not list the tracked files).")
            return 0
        if base_ref:
            reason, level = f"could not diff against '{base_ref}'", "::warning::"
        else:
            reason, level = "no base-ref given", ""
        print(
            f"{level}Skipping the single-ask part check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every part the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.exercises} exercise div(s) across {report.files} "
        f"file(s) (scope: {scope})."
    )
    severity = "error" if fail else "warning"
    for rel, line, asks in report.findings:
        print(f"::{severity} file={rel},line={line}::{format_message(asks)}")
    if not report.findings:
        print("No touched exercise part asks for more than one thing.")
        return 0
    print(f"\n{len(report.findings)} exercise part(s) ask for more than one thing.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
