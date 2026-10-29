#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a hybrid sentence: one condition in words and another in math.

The lab's rule (Ezra, 2026-10-29; psw ``chapters/mathematical-writing.qmd``,
"Write each sentence in words or in math, not both"): a sentence is entirely in
words, where single inline expressions are fine, or entirely in math. A sentence
such as "The risk is zero if and only if $\P(f = g) = 1$." states its first
condition in words and its second as a relation between expressions. Write two
complete sentences instead: one in words and one displayed in math.

The check reads each prose paragraph, outside code fences, display math, HTML
comments and paragraphs that contain a counter-example mark (the cross emoji). In
each sentence it looks at the connectives "if and only if", "iff", "and" and "or",
and flags the sentence when

- the clause on one side of a connective starts (or ends) with an inline relation
  between expressions (``=``, ``\neq``, ``<``, ``\le``, ``\subseteq``,
  ``\approx``, ``\iff`` and the like), and
- the clause on the other side holds three or more words and no such relation.

Two relations joined by a connective ("with $a = 1$ and $b = 2$") are all math and
are not flagged. The check is a heuristic: it is warn-only by default, and
``<!-- hybrid-ok: reason -->`` in the paragraph exempts it.

A paragraph is checked when the diff adds a line in it, or always with
``HS_WHOLE_TREE=true``. No base-ref means the run is skipped.

Configuration (environment variables, set by the composite action):
  HS_BASE_REF      Git ref/SHA to diff against; empty and not whole-tree => skip.
  HS_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  HS_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  HS_FAIL          "true" => blocking; default "false" (warning annotations).
  HS_WHOLE_TREE    "true" => check every paragraph in the tree.
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
    "state the result in one sentence in words and again in one displayed "
    "formula, or add <!-- hybrid-ok: reason --> to the paragraph"
)

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
DIV_RE = re.compile(r"^ {0,3}:{3,}")
COMMENT_RE = re.compile(r"<!--.*?--!?>", re.DOTALL)
ALLOW_RE = re.compile(r"<!--\s*hybrid-ok\b", re.IGNORECASE)
DISPLAY_RE = re.compile(r"\$\$.+?\$\$", re.DOTALL)
INLINE_RE = re.compile(r"(?<![\\$])\$(?!\$)((?:\\.|[^$\\])+?)\$")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
CONNECTIVE_RE = re.compile(r"^(?:if and only if|iff|and|or)$", re.IGNORECASE)
CONNECTIVES = ("if and only if", "iff", "and", "or")
RELATION_RE = re.compile(
    r"(?<![<>!:\\])=|\\(?:neq?|leq?|geq?|subseteq?|supseteq?|subset|supset|"
    r"approx|sim|equiv|iff|implies|ne)\b|(?<![\\-])[<>]")
OPEN, CLOSE = "([{", ")]}"
MIN_WORDS = 3


class Finding(NamedTuple):
    path: str
    line: int
    message: str


def paragraphs(lines: List[str]) -> List[Tuple[int, int, str]]:
    """(first line index, last line index, text) of each prose paragraph."""
    out: List[Tuple[int, int, str]] = []
    fence: Optional[Tuple[str, int]] = None
    cur: List[str] = []
    start = 0

    def flush(end: int) -> None:
        nonlocal cur
        if cur:
            out.append((start, end, "\n".join(cur)))
        cur = []

    for idx, raw in enumerate(lines):
        m = FENCE_RE.match(raw)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            flush(idx - 1)
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        stripped = raw.strip()
        if (not stripped or DIV_RE.match(raw) or stripped.startswith(("#", "|"))):
            flush(idx - 1)
            continue
        if not cur:
            start = idx
        cur.append(raw)
    flush(len(lines) - 1)
    return out


def top_level_relation(math: str) -> bool:
    """True when the math has a relation outside brackets and ``\\text``."""
    math = re.sub(r"\\(?:text|textrm|mathrm|operatorname)\{[^{}]*\}", " ", math)
    depth = 0
    flat: List[str] = []
    for i, c in enumerate(math):
        if i and math[i - 1] == "\\":
            flat.append(c if depth == 0 else " ")
            continue
        if c in OPEN:
            depth += 1
            flat.append(" ")
        elif c in CLOSE:
            depth = max(0, depth - 1)
            flat.append(" ")
        else:
            flat.append(c if depth == 0 else " ")
    # keep the backslash of a command so ``\in`` is not read as ``in``
    return bool(RELATION_RE.search("".join(flat)))


def tokens(sentence: str) -> List[str]:
    """Words, with each inline math span replaced by ``R`` (relation) or ``M``."""
    spans: List[str] = []

    def stash(m: "re.Match[str]") -> str:
        spans.append("R" if top_level_relation(m.group(1)) else "M")
        return f" \x00{len(spans) - 1}\x00 "

    masked = INLINE_RE.sub(stash, sentence)
    out: List[str] = []
    for tok in masked.split():
        m = re.fullmatch(r"\x00(\d+)\x00([.,;:)]*)", tok)
        if m:
            out.append(spans[int(m.group(1))])
            if m.group(2).startswith((",", ";", ":")):
                out.append(",")
            continue
        word = re.sub(r"[^A-Za-z',;:]", "", tok)
        if not word:
            continue
        trailing = word[-1] if word[-1] in ",;:" else ""
        core = word.rstrip(",;:").lower()
        if core:
            out.append("W:" + core)
        if trailing:
            out.append(",")
    return out


def connective_at(toks: List[str], i: int) -> int:
    """Length in tokens of a connective starting at ``i``, else 0."""
    for conn in CONNECTIVES:
        parts = conn.split()
        if [t[2:] if t.startswith("W:") else "" for t in toks[i:i + len(parts)]] == parts:
            return len(parts)
    return 0


def joiner_at(toks: List[str], i: int) -> int:
    """Length of a connective at ``i``, counting one comma just before it."""
    if toks[i:i + 1] == [","]:
        n = connective_at(toks, i + 1)
        return n + 1 if n else 0
    return connective_at(toks, i)


def segments(toks: List[str]) -> List[Tuple[int, int]]:
    """Token ranges between connectives and commas."""
    cuts: List[Tuple[int, int]] = []
    i, begin = 0, 0
    while i < len(toks):
        n = joiner_at(toks, i)
        if toks[i] == "," or n:
            cuts.append((begin, i))
            i += n or 1
            begin = i
        else:
            i += 1
    cuts.append((begin, len(toks)))
    return cuts


def words(seg: List[str]) -> int:
    return sum(1 for t in seg if t.startswith("W:"))


def hybrid(sentence: str) -> bool:
    toks = tokens(sentence)
    segs = segments(toks)
    for k in range(len(segs) - 1):
        left = toks[segs[k][0]:segs[k][1]]
        right = toks[segs[k + 1][0]:segs[k + 1][1]]
        end = segs[k][1]
        if not joiner_at(toks, end):
            continue
        if right[:1] == ["R"] and "R" not in left and words(left) >= MIN_WORDS:
            return True
        if left[-1:] == ["R"] and "R" not in right and words(right) >= MIN_WORDS:
            return True
    return False


def check_file(path: str, lines: List[str],
               touched: Optional[Set[int]]) -> List[Finding]:
    findings: List[Finding] = []
    for first, last, text in paragraphs(lines):
        if touched is not None and not any(n + 1 in touched
                                           for n in range(first, last + 1)):
            continue
        if ALLOW_RE.search(text) or "\u274c" in text:
            continue
        prose = COMMENT_RE.sub(" ", DISPLAY_RE.sub(" ", text))
        for sentence in SENTENCE_RE.split(prose):
            if hybrid(sentence):
                shown = " ".join(sentence.split())
                findings.append(Finding(path, first + 1,
                    f"hybrid sentence (heuristic): one condition is in words and "
                    f"another in math: \"{shown[:120]}\". A sentence is entirely in "
                    f"words or entirely in math. Fix: {ADVICE}"))
    return findings


# -- Git plumbing ------------------------------------------------------------

def _run_git(args: List[str]) -> Optional[str]:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    return res.stdout if res.returncode == 0 else None


_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_diff(diff: str) -> Dict[str, Set[int]]:
    """Added, non-blank line numbers per path."""
    added: Dict[str, Set[int]] = {}
    path: Optional[str] = None
    old_left = new_left = new_line = 0
    for line in diff.splitlines():
        if old_left > 0 or new_left > 0:
            if line.startswith("+"):
                if path is not None and line[1:].strip():
                    added[path].add(new_line)
                new_line += 1
                new_left -= 1
            elif line.startswith("-"):
                old_left -= 1
            continue
        if line.startswith("+++ "):
            target = line[4:].rstrip("\t")
            path = None if target == "/dev/null" else (
                target[2:] if target.startswith("b/") else target)
            if path is not None:
                added.setdefault(path, set())
            continue
        m = _HUNK_RE.match(line)
        if m:
            old_left = int(m.group(1)) if m.group(1) is not None else 1
            new_line = int(m.group(2))
            new_left = int(m.group(3)) if m.group(3) is not None else 1
    return added


def _glob_to_regex(pat: str) -> "re.Pattern[str]":
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


def _split_list(value: str) -> List[str]:
    return [p.strip() for p in re.split(r"[,\n]", value) if p.strip()]


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return default if not value else value in ("1", "true", "yes", "on")


def _read_lines(path: str) -> Optional[List[str]]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().split("\n")
    except OSError:
        return None
    if lines and lines[-1] == "":
        lines.pop()
    return lines


class Report(NamedTuple):
    findings: List[Finding]
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              whole_tree: bool) -> Report:
    out = _run_git(["ls-files", "--", *globs])
    if out is None:
        return Report([], True)
    names = [r for r in out.splitlines()
             if r and not any(g.match(r) for g in ignores)]
    touched: Optional[Dict[str, Set[int]]] = None
    if not whole_tree:
        if not base_ref:
            return Report([], True)
        base = _run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], True)
        diff = _run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                         "--src-prefix=a/", "--dst-prefix=b/",
                         base.strip(), "--", *globs])
        if diff is None:
            return Report([], True)
        touched = parse_diff(diff)
    findings: List[Finding] = []
    for rel in names:
        if touched is not None and not touched.get(rel):
            continue
        content = _read_lines(rel)
        if content is not None:
            findings.extend(check_file(rel, content,
                                       None if touched is None else touched[rel]))
    return Report(sorted(findings), False)



def main() -> int:
    base_ref = os.environ.get("HS_BASE_REF", "").strip()
    globs = os.environ.get("HS_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = compile_ignores(_split_list(os.environ.get("HS_PATHS_IGNORE", "")))
    fail = _env_flag("HS_FAIL", _DEFAULT_FAIL)
    whole_tree = _env_flag("HS_WHOLE_TREE", False)
    report = run_check(base_ref, globs, ignores, whole_tree)
    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(f"{'::warning::' if base_ref else ''}Skipping the hybrid-sentences "
              f"check for this run ({reason}; not falling back to a whole-tree scan).")
        return 0
    for f in report.findings:
        print(f"::{'error' if fail else 'warning'} file={f.path},line={f.line}::{f.message}")
    if not report.findings:
        print("No touched paragraph holds a sentence that mixes words and math conditions.")
        return 0
    print(f"\n{len(report.findings)} hybrid sentence(s).")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
