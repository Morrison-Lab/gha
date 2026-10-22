#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a div whose first sentence opens with an unlinked definite phrase.

The lab's rule (Ezra, 2026-10-19; Morrison-Lab/psw#291): a definite noun
phrase needs a clear antecedent, and a phrase whose antecedent is not in the
same div or passage links to where the antecedent is introduced.

A grammar-aware check is out of reach, so this is a heuristic for the clearest
case: the first sentence of a div's body (or of a file with no div) begins with
"The", "These", "Those", "This" or "That" and holds no link and no
cross-reference. Nothing earlier in that div can be the antecedent, so the
reader has none unless a link supplies one. The finding sits on that line.
It is warn-only: a definition that starts "The covariance function must be..."
is reported although it may be fine, which is why it never fails by default.

Not counted: code fences, HTML comments, YAML headers, headings, a first
sentence that defines a bolded term ("The **mean** of ..."), and a first
sentence holding a Markdown link, a ``@`` cross-reference or an include
shortcode. Diff-scoped by default: only a first sentence on an added line is
reported (an added line whose exact text was also deleted counts as moved).
With no base ref, or when the diff cannot be computed, the check skips with a
warning; ``ODA_WHOLE_TREE=true`` scans every tracked file instead.

Configuration (environment variables, set by the composite action):
  ODA_BASE_REF, ODA_GLOBS (default '*.qmd'), ODA_PATHS_IGNORE, ODA_FAIL
  (default false), ODA_WHOLE_TREE.
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

ADVICE = (
    "name the referent in this div, or link the phrase to where it is "
    "introduced, for example [the data](#exm-data)"
)

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
LIST_MARKER_RE = re.compile(r"^(?:[-*+]\s+|\d+[.)]\s+)")
DEFINITE_RE = re.compile(r"^(The|These|Those|This|That)\s+(?!\*\*)(\S+)")
LINKED_RE = re.compile(r"\]\(|(?<!\w)@[A-Za-z]+-|\{\{<")


class Hit(NamedTuple):
    line: int
    phrase: str


CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")


def drop_closed_comments(text: str) -> str:
    """Remove each ``<!-- ... -->`` pair from one line, leaving an open one."""
    while True:
        start = text.find("<!--")
        end = text.find("-->", start + 4) if start >= 0 else -1
        if end < 0:
            return text
        text = text[:start] + text[end + 3:]


def strip_comments(raw: str, in_comment: bool) -> Tuple[str, bool]:
    """Remove HTML comment text from one line; say whether one stays open.

    A ``<!--`` inside an inline code span is prose, not a comment, and text
    after a closing ``-->`` stays on the line.
    """
    if in_comment:
        end = raw.find("-->")
        if end < 0:
            return "", True
        raw = raw[end + 3:]
    spans: List[str] = []
    raw = CODE_SPAN_RE.sub(lambda m: spans.append(m.group(0)) or "\0", raw)
    raw = drop_closed_comments(raw)
    start = raw.find("<!--")
    opened = start >= 0
    if opened:
        raw = raw[:start]
    it = iter(spans)
    return re.sub("\0", lambda _: next(it), raw), opened


def first_sentence(text: str) -> str:
    m = re.search(r"[.!?:](?:\s|$)", text)
    return text[:m.end()] if m else text


def scan_file(lines: List[str]) -> Tuple[List[Hit], int]:
    """Unlinked definite openers of divs, and the divs (or files) examined."""
    hits: List[Hit] = []
    examined = 0
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    in_yaml = bool(lines) and lines[0].strip() == "---"
    waiting = not in_yaml  # looking for the first text line of a div or file
    if not in_yaml:
        examined += 1
    for idx, raw in enumerate(lines):
        if in_yaml:
            if idx > 0 and raw.strip() == "---":
                in_yaml, waiting = False, True
                examined += 1
            continue
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
            waiting = False
            continue
        dm = DIV_RE.match(raw)
        if dm:
            if dm.group(2):
                waiting = True
                examined += 1
            else:
                waiting = False
            continue
        text = raw.strip()
        if not waiting or not text or text.startswith("#"):
            continue
        waiting = False
        text = LIST_MARKER_RE.sub("", text)
        sentence = first_sentence(text)
        opener = DEFINITE_RE.match(sentence)
        if opener and not LINKED_RE.search(sentence):
            hits.append(Hit(idx + 1, f"{opener.group(1)} {opener.group(2)}"))
    return hits, examined


def format_message(phrase: str) -> str:
    return (f"This div opens with the definite phrase '{phrase} ...' and no "
            f"link, so no earlier text in the div can be its antecedent. "
            f"Fix: {ADVICE}")


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
    findings: List[Tuple[str, int, str]]  # (path, line, phrase)
    files: int
    lines: int
    divs: int
    skipped: bool


def _read_lines(path: str) -> Optional[List[str]]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().split("\n")
    except OSError:
        return None
    if lines and lines[-1] == "":
        lines.pop()  # the newline ending the file does not start a line
    return lines


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    """Scan files with an added line since ``base_ref``, or all when whole-tree."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = _run_git(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, 0, 0, True)
        for rel in out.splitlines():
            if rel and not _ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, 0, True)
        base = _run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, 0, True)
        diff = _run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                         base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, 0, True)
        added, deleted = parse_diff(diff)
        for rel, numbered in added.items():
            if _ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if text.strip() and text not in deleted}

    findings: List[Tuple[str, int, str]] = []
    files = lines = divs = 0
    for rel in sorted(wanted):
        content = _read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        hits, seen = scan_file(content)
        divs += seen
        for hit in hits:
            if keep is None or hit.line in keep:
                findings.append((rel, hit.line, hit.phrase))
    return Report(findings, files, lines, divs, False)


def main() -> int:
    base_ref = os.environ.get("ODA_BASE_REF", "").strip()
    globs = os.environ.get("ODA_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("ODA_PATHS_IGNORE", "")))
    fail = _env_flag("ODA_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("ODA_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        # With no base-ref (a push run) the skip is expected, so it is not an annotation.
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the definite-antecedent check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every div the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s), "
        f"{report.divs} div(s) or files (scope: {scope})."
    )
    severity = "error" if fail else "warning"
    for rel, line, phrase in report.findings:
        print(f"::{severity} file={rel},line={line}::{format_message(phrase)}")
    if not report.findings:
        print("No div opens with an unlinked definite phrase.")
        return 0
    print(f"\n{len(report.findings)} div(s) open with an unlinked definite phrase.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
