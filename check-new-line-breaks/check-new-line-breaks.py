#!/usr/bin/env python3
"""
Flag newly-added Markdown lines that pack more than one sentence/clause onto
a single source line -- an advisory nudge toward semantic line breaks (one
clause/sentence per line), not a hard style gate.

Design notes:
- **Diff-scoped by default.** When ``NLB_BASE_REF`` is set (a PR's base SHA),
  only lines *added* by the PR are checked, so a corpus that has already
  accumulated long lines (commonly because markdownlint's MD013 is disabled
  for exactly this reason) doesn't get reflagged on every unrelated edit.
  Otherwise the whole tracked tree is checked, which is what runs on
  ``push``.
- **If the diff can't be computed** (e.g. a shallow clone missing the base
  commit), the check is *skipped* with a warning rather than falling back to
  a whole-tree scan -- unlike ``check-phi``'s fallback, scanning the whole
  tree here would defeat the entire point (reflagging every pre-existing
  long line the corpus already carries).
- **Non-blocking by default** (``NLB_FAIL`` defaults to false): a long line
  can legitimately be un-splittable (a URL, a citation, a single genuinely
  long clause), so this is a nudge to consider a semantic break, not a gate.

Configuration (all via environment variables, set by the composite action):
  NLB_BASE_REF      Git ref/SHA to diff against. Empty => scan whole tree.
  NLB_GLOBS         Space-separated git pathspecs to check (default: '*.md').
  NLB_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  NLB_FAIL          "true" => exit 1 on findings; default "false" => warn only.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Set, Tuple

# ── Sentence splitting ──────────────────────────────────────────────────────

# Abbreviations whose trailing period should NOT trigger a sentence split.
_ABBREVS = [
    "e.g", "i.e", "vs", "etc", "Dr", "Mr", "Mrs", "Ms", "Jr", "Sr",
    "Fig", "Eq", "Ref", "Sec", "Ch", "Vol", "pp", "No", "approx",
    "incl", "excl", "ca", "cf", "ibid", "op", "pt", "Dept",
    "al",  # et al.
]
_ABBREV_RE = re.compile(r"(?<!\w)(" + "|".join(re.escape(a) for a in _ABBREVS) + r")\.")

# Sentence boundary: [.!?] + optional closing chars + whitespace + uppercase/quote.
_SENT_BREAK_RE = re.compile(r"([.!?][`\"')\]]*)\s+(?=[A-Z\"'`*\[])")

_PLACEHOLDER = "\x00"


def _protect_inline_code(m: "re.Match[str]") -> str:
    """Replace sentence-ending punctuation inside backtick spans with placeholders."""
    return m.group(0).replace(".", _PLACEHOLDER).replace("!", "\x01").replace("?", "\x02")


def split_sentences(text: str) -> List[str]:
    """Split text at sentence boundaries; return the list of sentences."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    protected = _ABBREV_RE.sub(lambda m: m.group(1) + _PLACEHOLDER, text)
    protected = re.sub(r"`[^`]+`", _protect_inline_code, protected)
    protected = _SENT_BREAK_RE.sub(lambda m: m.group(1) + "\n", protected)
    parts = [
        p.replace(_PLACEHOLDER, ".").replace("\x01", "!").replace("\x02", "?").strip()
        for p in protected.split("\n")
    ]
    return [p for p in parts if p]


# ── Block detectors (mirrors which lines a semantic-line-break pass would
# leave untouched: frontmatter, fenced code, tables, headings, horizontal
# rules, HTML comments, and blockquote structure lines) ────────────────────

_BULLET_RE = re.compile(r"^(\s*)([-*+]|\d+\.)\s+(.*)", re.DOTALL)
_HEADING_RE = re.compile(r"^\s*#{1,6}[\s#]")
_TABLE_RE = re.compile(r"^\s*\|")
_HR_RE = re.compile(r"^\s*[-*_]{3,}\s*$")
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_BQ_RE = re.compile(r"^\s*>")
_BLANK_RE = re.compile(r"^\s*$")
_HTML_COMMENT_RE = re.compile(r"^\s*<!--")


def prose_line_numbers(text: str) -> Set[int]:
    """1-indexed lines eligible for a sentence-count check.

    Excludes frontmatter, fenced code, tables, headings, horizontal rules,
    HTML comments, and @-import directives. Blockquote *prose* is included
    (checked), with only a bullet/blank/fenced-code line nested inside a
    blockquote excluded -- the same as at the top level.
    """
    lines = text.split("\n")
    prose: Set[int] = set()
    in_frontmatter = False
    frontmatter_done = False
    in_code = False
    fence_len = 0
    fence_char: Optional[str] = None
    in_html_comment = False
    in_bq_code = False

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()

        if not frontmatter_done and not in_frontmatter and idx == 1 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
                frontmatter_done = True
            continue

        if in_html_comment:
            if "-->" in line:
                in_html_comment = False
            continue
        if _HTML_COMMENT_RE.match(line):
            if "-->" not in line:
                in_html_comment = True
            continue

        fence_m = _FENCE_RE.match(stripped)
        if fence_m:
            fence_str = fence_m.group(1)
            fl, fc = len(fence_str), fence_str[0]
            if not in_code:
                in_code, fence_len, fence_char = True, fl, fc
            elif fc == fence_char and fl >= fence_len:
                in_code, fence_len, fence_char = False, 0, None
            continue
        if in_code:
            continue

        if _BQ_RE.match(line):
            inner = re.sub(r"^\s*>\s?", "", line)
            if _FENCE_RE.match(inner.strip()):
                in_bq_code = not in_bq_code
                continue
            if in_bq_code or _BULLET_RE.match(inner) or _BLANK_RE.match(inner):
                continue
            prose.add(idx)
            continue
        in_bq_code = False

        if (
            _BLANK_RE.match(line)
            or _HEADING_RE.match(line)
            or _TABLE_RE.match(line)
            or _HR_RE.match(stripped)
        ):
            continue

        prose.add(idx)

    return prose


def line_content(line: str) -> str:
    """Strip a bullet marker or blockquote prefix so the splitter sees plain prose."""
    bullet_m = _BULLET_RE.match(line)
    if bullet_m:
        return bullet_m.group(3)
    if _BQ_RE.match(line):
        return re.sub(r"^\s*>\s?", "", line).strip()
    return line.strip()


# ── Scope resolution ────────────────────────────────────────────────────────

def _run_git(args: List[str]) -> Optional[str]:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, check=True,
            encoding="utf-8", errors="replace",
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


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


def _compile_ignores(patterns: List[str]) -> List["re.Pattern[str]"]:
    compiled = []
    for pat in patterns:
        compiled.append(_glob_to_regex(pat))
        if "*" not in pat and "?" not in pat:
            compiled.append(_glob_to_regex(pat.rstrip("/") + "/**"))
    return compiled


def _ignored(rel: str, ignores: List["re.Pattern[str]"]) -> bool:
    return any(r.match(rel) for r in ignores)


def _tracked_files(pathspecs: List[str]) -> List[str]:
    out = _run_git(["ls-files", "--", *pathspecs])
    return [p for p in (out or "").splitlines() if p]


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _added_line_numbers(base_ref: str, pathspecs: List[str]) -> Optional[dict]:
    """Return {file: {new-file line numbers added}} vs the merge-base of
    base_ref and HEAD, or None if the diff could not be computed."""
    diff = _run_git(["diff", "--unified=0", "--no-color", f"{base_ref}...HEAD", "--", *pathspecs])
    if diff is None:
        return None
    result: dict = {}
    cur_path: Optional[str] = None
    new_lineno = 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:]
            cur_path = None if target == "/dev/null" else target[2:]
            if cur_path is not None:
                result.setdefault(cur_path, set())
            continue
        if raw.startswith("@@"):
            m = _HUNK_RE.match(raw)
            new_lineno = int(m.group(1)) if m else 0
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            if cur_path is not None:
                result[cur_path].add(new_lineno)
            new_lineno += 1
    return result


def find_violations(
    base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"]
) -> Tuple[List[Tuple[str, int, str]], bool]:
    """Return (violations, diff_unavailable). violations is empty and
    diff_unavailable is True when base_ref was set but the diff failed."""
    if base_ref:
        added = _added_line_numbers(base_ref, globs)
        if added is None:
            return [], True
        scope = added
    else:
        scope = {f: None for f in _tracked_files(globs)}  # None => whole file

    violations: List[Tuple[str, int, str]] = []
    for rel_path in sorted(scope):
        if _ignored(rel_path, ignores):
            continue
        path = Path(rel_path)
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lines = text.split("\n")
        prose = prose_line_numbers(text)
        added_lines = scope[rel_path]
        target_lines = prose if added_lines is None else (added_lines & prose)

        for line_no in sorted(target_lines):
            if line_no < 1 or line_no > len(lines):
                continue
            content = line_content(lines[line_no - 1])
            if len(split_sentences(content)) > 1:
                preview = content if len(content) <= 80 else content[:77] + "..."
                violations.append((rel_path, line_no, preview))
    return violations, False


# ── Main ─────────────────────────────────────────────────────────────────

def _split_list(value: str) -> List[str]:
    return [tok.strip() for tok in re.split(r"[,\n]", value or "") if tok.strip()]


def main() -> int:
    base_ref = os.environ.get("NLB_BASE_REF", "").strip()
    globs = os.environ.get("NLB_GLOBS", "*.md").split() or ["*.md"]
    ignore = _compile_ignores(_split_list(os.environ.get("NLB_PATHS_IGNORE", "")))
    fail = os.environ.get("NLB_FAIL", "false").strip().lower() == "true"

    violations, diff_unavailable = find_violations(base_ref, globs, ignore)

    if diff_unavailable:
        print(
            f"::warning::Could not diff against '{base_ref}'; skipping the "
            f"new-line-breaks check for this run (not falling back to a "
            f"whole-tree scan, which would reflag pre-existing long lines)."
        )
        return 0

    mode = f"lines added since {base_ref[:12]}" if base_ref else "whole tree"
    print(f"Checking for missing semantic line breaks ({mode})\n")

    if not violations:
        print("No lines missing semantic breaks.")
        return 0

    level = "error" if fail else "warning"
    for rel_path, line_no, preview in violations:
        print(f"::{level} file={rel_path},line={line_no}::"
              f"Line packs more than one sentence/clause: {preview}")

    print(
        f"\n{len(violations)} line(s) pack more than one sentence/clause. "
        f"Consider a semantic-break pass (one clause/sentence per line)."
    )
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
