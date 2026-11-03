#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a list of three or more items with no comma before the final "and"/"or".

The lab's rule (Ezra, 2026-11-03; Morrison-Lab/psw grammar chapter): put a
comma before the "and" or "or" that closes a list of three or more items,
as in "mean, median, and mode", so the reader never has to guess whether the
last two items form a pair.

What is flagged: after inline math, code, links and citations are reduced to
single-word placeholders, a sentence part ``A, B and C`` or ``A, B or C``
where the final comma is missing.
Not flagged: ``A, B, and C``; a two-item list; an introductory phrase
followed by a pair ("However, x and y", "In practice, a and b");
anything in a code fence, an HTML comment, YAML front matter, a table row,
or on a line carrying ``<!-- check-serial-comma: allow -->``.

A sentence can span source lines (semantic line breaks), so each paragraph is
joined before matching; a finding is reported on the line of the "and"/"or".
Diff-scoped like check-bare-yes-no: only an added line is reported, and with
no base ref the check skips rather than scanning the whole tree.
``SC_WHOLE_TREE=true`` measures a corpus.

Configuration (environment variables, set by the composite action):
  SC_BASE_REF    Git ref/SHA to diff against. Empty and not whole-tree => skip.
  SC_GLOBS       Space-separated git pathspecs (default: '*.qmd *.md').
  SC_FAIL        "false" => warnings only; default "true" => exit 1.
  SC_WHOLE_TREE  "true" => scan every tracked matching file in full.
"""

import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Set, Tuple

DEFAULT_GLOBS = "*.qmd *.md"
ALLOW = "check-serial-comma: allow"
ADVICE = ('add a comma before the final "and" or "or", as in "mean, median, and mode"; '
          "or put `<!-- check-serial-comma: allow -->` on the line")

# First word of a sentence that opens with an introductory phrase: the comma
# after it ends the phrase, so "<phrase>, A and B" is a pair, not a list.
INTRO_WORDS = frozenset("""
    however then thus hence so first second third finally next here there also
    instead now therefore similarly otherwise moreover furthermore additionally
    conversely indeed again yes no eg ie for in on at by with after before during
    as if when since because although though while whereas unless once until
    given suppose but and or which who whose where that under from to over across
    within without into through throughout between among about like unlike per
    using consider compared relative overall specifically typically usually
    often sometimes together alternatively meanwhile afterward later earlier
    still even only both either neither
""".split())

CLAUSE_WORDS = frozenset("""
    such including especially particularly notably namely example instance
    we you they it he she this these those is are was were has have had do does
    can will would should may might must
""".split())

FENCE_RE =re.compile(r"^[ \t]*(`{3,}|~{3,})")
DIV_RE = re.compile(r"^ {0,3}:{3,}")
MARKER_RE = re.compile(r"^[ \t]*(?:>[ \t]*)*(?:[-*+]|\d{1,2}[.)]|\(?[a-z][.)]|\([a-z]\))[ \t]+")
HEADING_RE = re.compile(r"^#{1,6}\s")
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
CONJ_RE = re.compile(r"\s(and|or)\s")
ABBREV_RE = re.compile(r"\b(e\.g|i\.e|vs|etc|cf|al|Fig|Eq|Sec|No)\.")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?:;])\s+")
# A conjunction that does not join list items.
NOT_ITEM = frozenset({"not", "so", "both", "vice"})


def clean(line: str) -> str:
    """Reduce one source line to plain words; math, code and the like become X."""
    line = re.sub(r"^[ \t]*(?:>[ \t]*)+", "", line)
    line = re.sub(r"[❌✅]", "", line)
    line = re.sub(r"<!--.*?-->", "", line)
    line = re.sub(r"\{\{<.*?>\}\}", "", line)
    line = re.sub(r"\\\$", "", line)
    line = re.sub(r"\$\$.*?\$\$|\$[^$]*\$", "X", line)
    line = re.sub(r"`[^`]*`", "X", line)
    line = re.sub(r"\[@[^\]]*\]", "", line)
    line = re.sub(r"@[A-Za-z][\w:.-]*", "X", line)
    line = re.sub(r"\]\([^)]*\)", "]", line)
    line = re.sub(r"[\[\]]", "", line)
    line = re.sub(r"<[^>]*>", "", line)
    line = re.sub(r"\{[^}]*\}", "", line)
    line = re.sub(r"https?://\S+", "X", line)
    line = ABBREV_RE.sub(lambda m: m.group(1).replace(".", ""), line)
    line = line.replace("**", "").replace("__", "")
    line = re.sub(r"(?<!\w)[*_]|[*_](?!\w)", "", line)
    line = re.sub(r"[“”\"]", "", line)
    return line.strip()


def paragraphs(lines: List[str]) -> List[List[Tuple[int, str]]]:
    """Paragraphs of ``(line number, cleaned text)``, skipping non-prose."""
    out: List[List[Tuple[int, str]]] = []
    cur: List[Tuple[int, str]] = []

    def flush() -> None:
        nonlocal cur
        if cur:
            out.append(cur)
        cur = []

    fence: Optional[str] = None
    in_comment = False
    front = bool(lines) and lines[0].strip() == "---"
    for idx, raw in enumerate(lines):
        number = idx + 1
        if front:
            if idx > 0 and raw.strip() in ("---", "..."):
                front = False
            flush()
            continue
        if in_comment:
            in_comment = "-->" not in raw
            flush()
            continue
        if raw.lstrip().startswith("<!--") and "-->" not in raw:
            in_comment = True
            flush()
            continue
        fm = FENCE_RE.match(raw)
        if fence is not None:
            if fm and fm.group(1)[0] == fence:
                fence = None
            flush()
            continue
        if fm:
            fence = fm.group(1)[0]
            flush()
            continue
        if not raw.strip() or DIV_RE.match(raw) or raw.lstrip().startswith("|"):
            flush()
            continue
        if ALLOW in raw:
            flush()
            continue
        if MARKER_RE.match(raw) or HEADING_RE.match(raw):
            flush()
            raw = MARKER_RE.sub("", raw, count=1) if MARKER_RE.match(raw) else HEADING_RE.sub("", raw, count=1)
        text = clean(raw)
        if text:
            cur.append((number, text))
    flush()
    return out


def missing_serial(sentence: str) -> Optional[int]:
    """Offset of the conjunction in ``A, B and C`` with no serial comma, else None."""
    parts = sentence.split(", ")
    offset = 0
    for i in range(len(parts) - 1):
        offset += len(parts[i]) + 2
        first = parts[i].strip()
        second = parts[i + 1]
        if not first or re.match(r"\s*(and|or|but)\b", second):
            continue
        if re.sub(r"\W", "", first.split()[-1]).lower() in ("eg", "ie"):
            continue
        m = CONJ_RE.search(" " + second + " ")
        if not m:
            continue
        padded = " " + second + " "
        item2 = padded[: m.start()].strip()
        item3 = padded[m.end():].strip()
        if not item2 or not item3 or len(item2.split()) > 4:
            continue
        if item3.split()[0].lower().strip(".,;:!?") in NOT_ITEM:
            continue
        if i == 0 and re.sub(r"\W", "", first.split()[0]).lower() in INTRO_WORDS:
            continue
        # "A, such as B or C", "A, which uses B or C": the second part opens a
        # phrase or clause, not a list item.
        if re.sub(r"\W", "", item2.split()[0]).lower() in INTRO_WORDS | CLAUSE_WORDS:
            continue
        return offset + m.start(1) - 1
    return None


def findings(lines: List[str]) -> List[Tuple[int, str]]:
    """``(line number of the conjunction, sentence)`` for each missing serial comma."""
    found: List[Tuple[int, str]] = []
    for para in paragraphs(lines):
        text = ""
        starts: List[Tuple[int, int]] = []
        for number, chunk in para:
            starts.append((len(text), number))
            text += chunk + " "
        pos = 0
        for sentence in SENTENCE_SPLIT_RE.split(text):
            at = text.find(sentence, pos)
            pos = at + len(sentence)
            where = missing_serial(sentence)
            if where is None:
                continue
            hit = at + where
            line = starts[0][1]
            for offset, number in starts:
                if offset <= hit:
                    line = number
            found.append((line, sentence.strip()))
    return found


def added_lines(diff: str) -> Dict[str, Set[int]]:
    """Added line numbers per path from ``git diff -U0`` output."""
    added: Dict[str, Set[int]] = {}
    path: Optional[str] = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].rstrip("\t")
            path = None if target == "/dev/null" else target.removeprefix("b/")
            if path is not None:
                added.setdefault(path, set())
            continue
        m = HUNK_RE.match(line)
        if m and path is not None:
            start = int(m.group(1))
            count = 1 if m.group(2) is None else int(m.group(2))
            added[path].update(range(start, start + count))
    return added


def _git(args: List[str]) -> Optional[str]:
    res = subprocess.run(["git", "-c", "core.quotepath=false", *args],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", errors="replace")
    return res.stdout if res.returncode == 0 else None


def wanted_lines(base_ref: str, globs: List[str], whole_tree: bool
                 ) -> Optional[Dict[str, Optional[Set[int]]]]:
    """Files to scan, each with its added lines (None = every line)."""
    if whole_tree:
        out = _git(["ls-files", "--", *globs])
        return None if out is None else {p: None for p in out.splitlines() if p}
    if not base_ref:
        return None
    base = _git(["merge-base", base_ref, "HEAD"])
    if not base or not base.strip():
        return None
    diff = _git(["diff", "-U0", "--no-color", "--no-ext-diff", base.strip(),
                 "--", *globs])
    return None if diff is None else dict(added_lines(diff))


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return default if not value else value in ("1", "true", "yes", "on")


def main() -> int:
    base_ref = os.environ.get("SC_BASE_REF", "").strip()
    globs = os.environ.get("SC_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    fail = _flag("SC_FAIL", True)
    whole = _flag("SC_WHOLE_TREE", False)
    wanted = wanted_lines(base_ref, globs, whole)
    if wanted is None:
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the serial comma check for this run "
              f"({'could not diff against ' + repr(base_ref) if base_ref else 'no base-ref given'}).")
        return 0
    severity = "error" if fail else "warning"
    count = 0
    for rel in sorted(wanted):
        try:
            with open(rel, encoding="utf-8", errors="replace") as handle:
                lines = handle.read().split("\n")
        except OSError:
            continue
        keep = wanted[rel]
        for number, text in findings(lines):
            if keep is None or number in keep:
                count += 1
                print(f"::{severity} file={rel},line={number}::No comma before the "
                      f"final 'and' or 'or' of a list ('{text[:60]}'). Fix: {ADVICE}")
    print(f"Examined {len(wanted)} file(s); {count} missing serial comma(s) flagged.")
    return 1 if count and fail else 0


if __name__ == "__main__":
    sys.exit(main())
