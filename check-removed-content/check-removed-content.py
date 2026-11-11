#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a PR that removes prose which reappears nowhere in the PR.

The lab's rule (Ezra, 2026-11-09, review of Morrison-Lab/lds#2032; gha#1791):
content is moved, never deleted. A removed sentence must show up again among
the lines the PR adds, in any file (a move to another file, an outtakes
subfile, or a reworded version), or the PR must say that the removal is
intended.

How a removed sentence is matched. Lines are normalized (markup, math,
punctuation and case dropped, whitespace collapsed) and cut into sentences, so
a reflow or a change of semantic line breaks does not count as a removal. A
removed sentence passes when at least ``RCO_MIN_OVERLAP`` (default 0.6) of its
word trigrams occur among the trigrams of the added lines, so a lightly
reworded sentence passes while a deleted one does not. Sentences shorter than
``RCO_MIN_WORDS`` (default 5) words, headings, code, YAML, includes, tables
and display math are not examined.

Opt-outs (a removal that is deliberate):
  * ``removed-content-ok: reason`` anywhere in the PR body (``RCO_PR_BODY``)
    or in an added line (typically an HTML comment), for the whole PR.
  * A deleted file whose path or file name the PR body names is exempt.

Diff-scoped: with no base ref the check skips rather than examining history.

Configuration (environment variables, set by the composite action):
  RCO_BASE_REF     Git ref/SHA to diff against. Empty => skip.
  RCO_GLOBS        Space-separated git pathspecs (default: '*.qmd *.md').
  RCO_FAIL         "true" (default) => exit 1 on a finding; "false" => warnings.
  RCO_PR_BODY      The pull request body, searched for the opt-out marker.
  RCO_MIN_OVERLAP  Trigram overlap that counts as present (default 0.6).
  RCO_MIN_WORDS    Fewest words of an examined sentence (default 5).
"""

import os
import re
import subprocess
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

DEFAULT_GLOBS = "*.qmd *.md"
ADVICE = ("move the content (to a subfile, another page, or an outtakes file) "
          "or write 'removed-content-ok: reason' in the PR body")

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
OK_RE = re.compile(r"removed-content-ok:", re.I)
# In a file the marker counts only as an HTML comment, so prose that documents
# it (this check's own pages) does not silence the check.
ADDED_OK_RE = re.compile(r"<!--\s*removed-content-ok:", re.I)
SKIP_LINE_RE = re.compile(
    r"^\s*(?::::*|```|~~~|\{\{<|#\||<!--|\||---+\s*$|#{1,6}\s|\$\$|!\[|\[\^)")
MATH_RE = re.compile(r"\$\$.*?\$\$|\$[^$\n]+\$")
LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
MARKUP_RE = re.compile(r"[*_`~]|\{[^}]*\}|<[^>]+>|@[\w-]+|\[@[^\]]*\]")
SENT_RE = re.compile(r"(?<=[.!?])\s+")


class Removed(NamedTuple):
    path: str
    line: int
    text: str


def normalize(text: str) -> List[str]:
    """Lower-case word tokens of ``text`` with markup, links' targets and math dropped."""
    text = MATH_RE.sub(" ", text)
    text = LINK_RE.sub(r"\1", text)
    text = MARKUP_RE.sub(" ", text)
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())


def trigrams(words: List[str]) -> Set[Tuple[str, ...]]:
    return {tuple(words[i:i + 3]) for i in range(len(words) - 2)}


def parse_diff(diff: str) -> Tuple[List[Removed], List[str], Dict[str, bool]]:
    """Removed lines (with old numbers), added lines, and deleted-file flags."""
    removed: List[Removed] = []
    added: List[str] = []
    deleted: Dict[str, bool] = {}
    old_path: Optional[str] = None
    old_no = old_left = new_left = 0
    for line in diff.splitlines():
        # A hunk's own line counts say how many lines are content, so a removed
        # line starting "-- " or an added one starting "++ " is not a header.
        if old_left > 0 and line.startswith("-"):
            old_left -= 1
            removed.append(Removed(old_path or "", old_no, line[1:]))
            old_no += 1
        elif new_left > 0 and line.startswith("+"):
            new_left -= 1
            added.append(line[1:])
        elif line.startswith("--- "):
            target = line[4:].rstrip("\t")
            old_path = None if target == "/dev/null" else target.removeprefix("a/")
        elif line.startswith("+++ "):
            if line[4:].rstrip("\t") == "/dev/null" and old_path:
                deleted[old_path] = True
        elif (m := HUNK_RE.match(line)):
            old_no = int(m.group(1))
            old_left = int(m.group(2) if m.group(2) is not None else 1)
            new_left = int(m.group(4) if m.group(4) is not None else 1)
    return removed, added, deleted


def non_prose_lines(text: str) -> Set[int]:
    """1-based numbers of the lines inside fenced code or YAML front matter."""
    lines = text.splitlines()
    skip: Set[int] = set()
    start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                skip.update(range(1, i + 2))
                start = i + 1
                break
    fence = ""
    for i in range(start, len(lines)):
        m = re.match(r"^\s*(`{3,}|~{3,})", lines[i])
        if fence:
            skip.add(i + 1)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = ""
        elif m:
            fence = m.group(1)
            skip.add(i + 1)
    return skip


def sentences_of(removed: List[Removed], min_words: int
                 ) -> List[Tuple[str, int, str, List[str]]]:
    """(path, first line, snippet, words) for each examined removed sentence.

    Consecutive removed lines of one file are joined before splitting, so a
    sentence broken across lines is examined whole.
    """
    out: List[Tuple[str, int, str, List[str]]] = []
    run: List[Removed] = []

    def flush() -> None:
        if not run:
            return
        text = " ".join(r.text.strip() for r in run)
        for sent in SENT_RE.split(text):
            words = normalize(sent)
            if sum(1 for w in words if w.isalpha() and len(w) > 1) >= min_words:
                out.append((run[0].path, run[0].line, sent.strip(), words))
        run.clear()

    for item in removed:
        if SKIP_LINE_RE.match(item.text) or not item.text.strip():
            flush()
            continue
        if run and (item.path != run[-1].path or item.line != run[-1].line + 1):
            flush()
        run.append(item)
    flush()
    return out


def missing(removed: List[Removed], added: List[str], min_overlap: float,
            min_words: int) -> List[Tuple[str, int, str]]:
    """Removed sentences whose trigrams are not found among the added lines."""
    pool = trigrams(normalize(" ".join(a.strip() for a in added)))
    found: List[Tuple[str, int, str]] = []
    for path, line, snippet, words in sentences_of(removed, min_words):
        grams = trigrams(words)
        if not grams:
            continue
        if len(grams & pool) / len(grams) < min_overlap:
            found.append((path, line, snippet))
    return found


def exempt_deleted(path: str, body: str) -> bool:
    """Whether the PR body names the deleted file (by path or file name)."""
    names = (path, os.path.basename(path))
    return any(re.search(r"(?<![\w./-])" + re.escape(n) + r"(?![\w-])", body)
               for n in names)


def _git(args: List[str]) -> Optional[str]:
    res = subprocess.run(["git", "-c", "core.quotepath=false", *args],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", errors="replace")
    return res.stdout if res.returncode == 0 else None


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return default if not value else value in ("1", "true", "yes", "on")


def _number(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def merge_base(base_ref: str) -> Optional[str]:
    """The merge base of ``base_ref`` and HEAD, or None when it cannot be found."""
    out = _git(["merge-base", base_ref, "HEAD"]) if base_ref else None
    return out.strip() if out and out.strip() else None


def diff_since(base: str, globs: List[str]) -> Optional[str]:
    """``git diff -U0`` of the PR's changes since ``base``."""
    return _git(["diff", "-U0", "--no-color", "--no-ext-diff", "-M",
                 base, "HEAD", "--", *globs])


def prose_only(removed: List[Removed], base: str) -> List[Removed]:
    """Drop removed lines that sat inside fenced code or YAML front matter."""
    skips: Dict[str, Set[int]] = {}
    for path in {r.path for r in removed}:
        old = _git(["show", f"{base}:{path}"])
        skips[path] = non_prose_lines(old) if old else set()
    return [r for r in removed if r.line not in skips[r.path]]


def main() -> int:
    base_ref = os.environ.get("RCO_BASE_REF", "").strip()
    globs = os.environ.get("RCO_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    fail = _flag("RCO_FAIL", True)
    body = os.environ.get("RCO_PR_BODY", "")
    base = merge_base(base_ref)
    diff = diff_since(base, globs) if base else None
    if diff is None or base is None:
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the removed-content check for this run "
              f"({'could not diff against ' + repr(base_ref) if base_ref else 'no base-ref given'}).")
        return 0
    removed, added, deleted = parse_diff(diff)
    if OK_RE.search(body) or any(ADDED_OK_RE.search(a) for a in added):
        print(f"removed-content-ok marker found; {len(removed)} removed line(s) not examined.")
        return 0
    removed = prose_only([r for r in removed
                          if not (deleted.get(r.path) and exempt_deleted(r.path, body))],
                         base)
    found = missing(removed, added, _number("RCO_MIN_OVERLAP", 0.6),
                    int(_number("RCO_MIN_WORDS", 5)))
    severity = "error" if fail else "warning"
    for path, line, snippet in found:
        shown = snippet if len(snippet) <= 100 else snippet[:97] + "..."
        print(f"::{severity} file={path},line={line}::Removed text appears nowhere "
              f"in this PR: '{shown}'. Fix: {ADVICE}")
    print(f"Examined {len(removed)} removed line(s); {len(found)} sentence(s) "
          f"not found among the added lines.")
    return 1 if found and fail else 0


if __name__ == "__main__":
    sys.exit(main())
