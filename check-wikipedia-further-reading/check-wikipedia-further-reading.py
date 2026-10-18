#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag Wikipedia pages listed in a Further reading section.

The lab's rule (Ezra, 2026-10-18; Morrison-Lab/gha#1093): Wikipedia pages
never appear in a Further reading section. They are citations only, in prose.

What is flagged, in ``.qmd``/``.md`` files: a list item (starting with ``-``,
``*``, ``+`` or ``1.``) that cites or links Wikipedia, that is, it contains a
``@wikipedia_<key>`` citation, a link or URL to ``wikipedia.org``, or the words
``Wikipedia on``, when the item lies in a reading context:

- a section whose nearest preceding heading matches ``further reading``,
  ``online references``, ``going further``, ``additional reading``,
  ``learn more`` or the word ``reading``;
- a ``::: {.reading}`` div (the lab's class for a reading list);
- any part of a file whose name contains ``further-reading`` or
  ``sec-reading``. A subfile has its heading in the parent chapter, so the
  filename is all the check can see; the whole file counts.

What is not flagged: a Wikipedia citation in ordinary prose (a paragraph, or a
list item outside a reading context); code fences; a section after a later
heading that does not match (the nearest heading decides, so a following
``## Exercises`` resets the context).

Design notes, in the model of ``check-literal-math-letters``:

- **Diff-scoped by default.** Only list items with a line *added* since
  ``WFR_BASE_REF`` are reported. The whole file is parsed (the heading sits
  far above the item), and only findings on added lines are kept. An added
  line whose exact text was also deleted in the same diff is treated as moved,
  not new.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed (a shallow clone), the check skips with a warning.
  ``WFR_WHOLE_TREE=true`` asks for the whole tree explicitly.
- **Working-tree-aware.** The diff runs from the merge base to the working
  tree, so a staged or unstaged edit is examined. A brand new untracked file is
  invisible to ``git diff``; stage it to have it examined.
- **Blocking by default** (``WFR_FAIL`` defaults to true), like
  ``check-new-line-breaks``.
- **The search space is reported**: files, lines and list items examined.

Configuration (environment variables, set by the composite action):
  WFR_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  WFR_GLOBS         Space-separated git pathspecs (default: '*.qmd *.md').
  WFR_PATHS_IGNORE  Comma/newline-separated glob patterns (relative paths) to
                    skip. Supports ``*``, ``?`` and recursive ``**``.
  WFR_FAIL          "false" => annotate with warnings only; default "true" =>
                    exit 1 on a finding.
  WFR_WHOLE_TREE    "true" => scan every tracked matching file in full.
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
_DEFAULT_FAIL = True

# -- Rule tables -------------------------------------------------------------

READING_HEADING_RE = re.compile(
    r"further reading|online references|going further|additional reading"
    r"|learn more|\breading\b",
    re.IGNORECASE,
)
READING_FILENAME_RE = re.compile(r"further-reading|sec-reading")

# A Wikipedia citation, link, autolink, or the words "Wikipedia on".
WIKIPEDIA_RE = re.compile(
    r"@wikipedia_\w|wikipedia\.org|\bWikipedia\s+on\b", re.IGNORECASE
)

ADVICE = (
    "Wikipedia pages are citations only and never belong in Further reading; "
    "cite the page in prose with [@wikipedia_<key>] and list a textbook, "
    "paper or course here instead"
)

# -- Parsing -----------------------------------------------------------------

FENCE_RE = re.compile(r"^[ \t>]*(`{3,}|~{3,})(.*)$")
HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
ITEM_RE = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])[ \t]+(.*)$")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
READING_CLASS_RE = re.compile(r"(?:^|[\s{])\.reading(?=[\s}]|$)")


class Finding(NamedTuple):
    line: int
    text: str


def filename_is_reading(path: str) -> bool:
    return bool(READING_FILENAME_RE.search(os.path.basename(path)))


def scan_file(lines: List[str], path: str = "") -> Tuple[List[Finding], int]:
    """Findings (one per list item) and the number of list items in context.

    A finding's ``line`` is the item's first line. ``scan_file_items`` gives
    the line range of each finding, for diff scoping.
    """
    items = scan_items(lines, path)
    return ([Finding(first, text) for first, _last, text in items[0]],
            items[1])


def scan_items(lines: List[str], path: str = ""
               ) -> Tuple[List[Tuple[int, int, str]], int]:
    """``[(first_line, last_line, text)]`` of flagged items, and items seen."""
    by_name = filename_is_reading(path)
    in_context_by_heading = False
    fence: Optional[Tuple[str, int]] = None
    divs: List[Tuple[int, bool]] = []  # (colon count, is .reading)
    found: List[Tuple[int, int, str]] = []
    seen = 0
    current: Optional[List] = None  # [first, last, indent, [texts], context]

    def close() -> None:
        nonlocal current, seen
        if current is None:
            return
        first, last, _indent, texts, context = current
        current = None
        if not context:
            return
        seen += 1
        body = " ".join(texts)
        if WIKIPEDIA_RE.search(body):
            found.append((first, last, texts[0].strip()))

    for idx, raw in enumerate(lines):
        lineno = idx + 1
        m = FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        if m:
            close()
            fence = (m.group(1)[0], len(m.group(1)))
            continue

        h = HEADING_RE.match(raw)
        if h:
            close()
            in_context_by_heading = bool(READING_HEADING_RE.search(h.group(2)))
            continue

        dm = DIV_RE.match(raw)
        if dm:
            close()
            colons, attrs = len(dm.group(1)), dm.group(2)
            if attrs:
                divs.append((colons, bool(READING_CLASS_RE.search(attrs))))
            elif divs:
                divs.pop()
            continue

        context = (by_name or in_context_by_heading
                   or any(is_reading for _c, is_reading in divs))

        im = ITEM_RE.match(raw)
        if im:
            close()
            current = [lineno, lineno, len(im.group(1)), [im.group(2)], context]
            continue
        if current is not None:
            if not raw.strip():
                # A blank line ends the item unless the next text is indented;
                # a lazy look-ahead keeps this simple: the next non-blank line
                # decides.
                nxt = next((x for x in lines[idx + 1:] if x.strip()), "")
                if (len(nxt) - len(nxt.lstrip())) > current[2] and not ITEM_RE.match(nxt):
                    continue
                close()
                continue
            if (len(raw) - len(raw.lstrip())) > current[2]:
                current[1] = lineno
                current[3].append(raw)
                continue
            close()
    close()
    return found, seen


# -- Messages ----------------------------------------------------------------

def format_message(text: str) -> str:
    shown = text if len(text) <= 80 else text[:77] + "..."
    return f"Wikipedia in a Further reading list ({shown}). Fix: {ADVICE}"


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
    findings: List[Tuple[str, int, str]]
    files: int
    lines: int
    items: int
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


def select_findings(items: List[Tuple[int, int, str]],
                    keep: Optional[Set[int]]) -> List[Tuple[int, str]]:
    """Items with at least one kept (added, not moved) line, reported at the
    first such line. ``keep=None`` keeps every line (whole-tree mode)."""
    out = []
    for first, last, text in items:
        if keep is None:
            out.append((first, text))
            continue
        hit = [n for n in range(first, last + 1) if n in keep]
        if hit:
            out.append((hit[0], text))
    return out


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    """Scan the added lines since ``base_ref``, or every line when whole-tree."""
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
                           if not (text.strip() and text in deleted)}

    findings: List[Tuple[str, int, str]] = []
    files = lines = items = 0
    for rel in sorted(wanted):
        content = _read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        found, seen = scan_items(content, rel)
        items += seen
        for line, text in select_findings(found, keep):
            findings.append((rel, line, text))
    return Report(findings, files, lines, items, False)


def main() -> int:
    base_ref = os.environ.get("WFR_BASE_REF", "").strip()
    globs = os.environ.get("WFR_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("WFR_PATHS_IGNORE", "")))
    fail = _env_flag("WFR_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("WFR_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(
            f"::warning::Skipping the wikipedia-further-reading check for this "
            f"run ({reason}; not falling back to a whole-tree scan, which "
            f"would reflag every entry the corpus already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s), "
        f"{report.items} list item(s) in reading context (scope: {scope})."
    )
    if not report.findings:
        print("No Wikipedia pages in Further reading.")
        return 0

    severity = "error" if fail else "warning"
    for rel, line, text in report.findings:
        print(f"::{severity} file={rel},line={line}::{format_message(text)}")
    print(f"\n{len(report.findings)} list item(s) put Wikipedia in Further reading.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
