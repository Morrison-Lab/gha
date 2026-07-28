#!/usr/bin/env python3
"""
Flag newly-added Markdown lines that pack more than one sentence/clause onto
a single source line -- an advisory nudge toward semantic line breaks (one
clause/sentence per line), not a hard style gate.

Design notes:
- **Diff-scoped, always.** Only lines *added* since ``NLB_BASE_REF`` (a PR's
  base SHA) are checked, so a corpus that has already accumulated long lines
  (commonly because markdownlint's MD013 is disabled for exactly this
  reason) never gets reflagged on every unrelated edit.
- **No base_ref to diff against, or the diff can't be computed** (e.g. an
  unset base-ref on a push run, or a shallow clone missing the base commit):
  the check is *skipped* with a warning. There is no whole-tree fallback,
  unlike ``check-phi`` -- unlike PHI scanning, this check's entire purpose is
  to avoid ever reflagging pre-existing drift, so a whole-tree scan here
  would defeat the point, not just be less precise.
- **Non-blocking by default** (``NLB_FAIL`` defaults to false): a long line
  can legitimately be un-splittable (a URL, a citation, a single genuinely
  long clause), so this is a nudge to consider a semantic break, not a gate.
- **Two checks, both on by default.** Rule 4 of the SemBr spec (the
  normative MUST: break after a sentence) always applies. A narrow slice of
  rule 5 (the SHOULD: break after an independent clause) applies too, and is
  opt-*out* via ``NLB_CLAUSE_BREAKS=false`` -- see ``has_unbroken_clause``
  for why that slice is semicolons only, and why it is gated on line length.
  Defaulting it on is safe because the whole check is warn-only unless
  ``NLB_FAIL`` is set, so it adds annotations rather than build failures.

Configuration (all via environment variables, set by the composite action):
  NLB_BASE_REF      Git ref/SHA to diff against. Empty => skip the check.
  NLB_GLOBS         Space-separated git pathspecs to check (default: '*.md').
  NLB_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  NLB_FAIL          "true" => exit 1 on findings; default "false" => warn only.
  NLB_CLAUSE_BREAKS "false" => skip the clause check; default "true" =>
                    also flag long lines joining independent clauses with a
                    semicolon.
  NLB_CLAUSE_MIN_LENGTH
                    Minimum *visible* line length before the clause check
                    applies, inclusive (default: 80); markup is stripped
                    first. Ignored when NLB_CLAUSE_BREAKS is false.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional, Set, Tuple

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


# ── Clause breaks (on by default; SemBr rule 5) ─────────────────────────────

# Markup carries punctuation that is not prose: `python3 -m`, a `;`-separated
# shell command, a URL's query string, an HTML entity's own trailing `;`.
# Strip all of it before looking for a clause boundary, or CLI flags and URLs
# dominate the hits.
#
# Order matters: link targets go before bare URLs, so `[text](url)` has
# already become `[text]` and leaves no URL behind.
_CODE_SPAN_RE = re.compile(r"`[^`]*`")
_LINK_TARGET_RE = re.compile(r"\]\([^)]*\)")
_AUTOLINK_RE = re.compile(r"<https?://[^>\s]*>")
_BARE_URL_RE = re.compile(r"https?://\S+")
_ENTITY_RE = re.compile(
    r"&(?:[A-Za-z][A-Za-z0-9]{1,31}|#[0-9]{1,7}|#[xX][0-9A-Fa-f]{1,6});"
)
# One home for each default; action.yml and the reusable workflow declare
# the same two values, and a test pins all of them together.
_DEFAULT_CLAUSE_BREAKS = True
_DEFAULT_CLAUSE_MIN_LENGTH = 80


def strip_inline_markup(text: str) -> str:
    """Drop non-prose markup, leaving the prose around it.

    Removes inline code spans, link targets, autolinks, bare URLs, and HTML
    character entities -- every construct that can carry a ``;`` that is not a
    clause boundary, or inflate a line's length without adding visible text.

    Stripping only ever *removes* characters, so the result is a conservative
    lower bound on a line's visible length: an entity renders as one glyph and
    a code span as its contents, and both are removed outright. Under-counting
    can only suppress a flag, never invent one, which is the safe direction for
    an advisory check.
    """
    # `]` keeps a bracketed link's visible text attached to its own sentence.
    text = _CODE_SPAN_RE.sub("", text)
    text = _LINK_TARGET_RE.sub("]", text)
    for pattern in (_AUTOLINK_RE, _BARE_URL_RE, _ENTITY_RE):
        text = pattern.sub("", text)
    return text


def has_unbroken_clause(text: str, min_length: int = _DEFAULT_CLAUSE_MIN_LENGTH) -> bool:
    """True when ``text`` joins independent clauses that a break would separate.

    The SemBr spec's rule 5 asks for a break "after an independent clause as
    punctuated by a comma (,), semicolon (;), colon (:), or em dash". The
    punctuation marks how such a clause ends; it is not itself the trigger,
    and only the semicolon is a usable proxy without parsing:

    - A **comma** is overwhelmingly a list separator, an appositive, or an
      introductory phrase -- rule 6's MAY at most. Measured over a
      22,820-line semantic-line-break-conformant corpus, keying on any
      mid-line ``, ; : --`` flags 50.5% of already-conforming lines, against
      6.1% for the semicolon alone, and 0.7% once the length gate below
      applies. These are a re-measurement taken against the shipped code;
      d-morrison/gha#336 records the original pass, whose figures differ
      because the corpus grew and because the stripping below was widened
      after it was written.
    - A **colon** usually introduces a list or an example, which rule 7
      already breaks before, since the list starts on the next line.
    - A **dash** is usually a paired parenthetical (``X --- Y --- Z``), where
      breaking at the first dash but not the second is wrong.

    The length gate is what separates a genuinely overlong clause chain from
    an ordinary short line that merely contains a semicolon, and it degrades
    gracefully -- a long line with no break opportunity never flags.
    It measures the *stripped* length, so a line that is only long because of
    a code span, a link target, a bare URL, or an autolink does not qualify --
    matching the URL-inflation exception in ai-config's own
    semantic-line-breaks guidance.
    ``min_length`` is inclusive: a line of exactly that many visible
    characters is checked.
    """
    stripped = strip_inline_markup(text).rstrip()
    if len(stripped) < min_length:
        return False
    semicolon = stripped.find(";")
    return semicolon != -1 and semicolon < len(stripped) - 1


def classify_line(
    content: str,
    clause_breaks: bool = _DEFAULT_CLAUSE_BREAKS,
    clause_min_length: int = _DEFAULT_CLAUSE_MIN_LENGTH,
) -> Optional[str]:
    """Return the reason ``content`` is flagged, or None when it is clean.

    Rule 4 (the MUST) is checked first, so a line that breaks both rules is
    reported once, against the stronger one.
    """
    if len(split_sentences(content)) > 1:
        return "sentence"
    if clause_breaks and has_unbroken_clause(content, clause_min_length):
        return "clause"
    return None


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

    Excludes frontmatter, fenced code, tables, headings, and horizontal
    rules, and HTML comments. (Ported from d-morrison/ai-config's
    semantic-line-breaks.py, which also excludes ai-config's own
    ``@shared/foo.md``-style include directives -- not carried over here,
    since that convention has no equivalent in this repo's own consumers.)
    Blockquote *prose* is included (checked), with only a bullet/blank/
    fenced-code line nested inside a blockquote excluded -- the same as at
    the top level.
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


class Violation(NamedTuple):
    """One flagged line. ``reason`` names which check flagged it."""

    path: str
    line: int
    preview: str
    reason: str = "sentence"


_REASON_MESSAGES = {
    "sentence": "Line packs more than one sentence/clause",
    "clause": "Line joins independent clauses with a semicolon",
}


def find_violations(
    base_ref: str,
    globs: List[str],
    ignores: List["re.Pattern[str]"],
    clause_breaks: bool = _DEFAULT_CLAUSE_BREAKS,
    clause_min_length: int = _DEFAULT_CLAUSE_MIN_LENGTH,
) -> Tuple[List[Violation], bool]:
    """Return (violations, skipped). violations is empty and skipped is True
    whenever there's no diff to check against -- either base_ref was never
    given (e.g. a push run with no PR to diff against), or a base_ref was
    given but the diff could not be computed (e.g. a shallow clone). Unlike
    check-phi, there is no whole-tree fallback: this check's entire purpose
    is to avoid ever reflagging a corpus's pre-existing long lines, so a
    whole-tree scan here would defeat the point, not just be less precise.
    """
    if not base_ref:
        return [], True
    scope = _added_line_numbers(base_ref, globs)
    if scope is None:
        return [], True

    violations: List[Violation] = []
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
        target_lines = scope[rel_path] & prose

        for line_no in sorted(target_lines):
            if line_no < 1 or line_no > len(lines):
                continue
            content = line_content(lines[line_no - 1])
            reason = classify_line(content, clause_breaks, clause_min_length)
            if reason is not None:
                preview = content if len(content) <= 80 else content[:77] + "..."
                violations.append(Violation(rel_path, line_no, preview, reason))
    return violations, False


# ── Main ─────────────────────────────────────────────────────────────────

def _split_list(value: str) -> List[str]:
    return [tok.strip() for tok in re.split(r"[,\n]", value or "") if tok.strip()]


def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean env var, falling back to ``default`` when unset/empty."""
    raw = os.environ.get(name, "").strip().lower()
    return default if not raw else raw == "true"


def _env_int(name: str, default: int) -> int:
    """Read an int env var, falling back to ``default`` when unset or invalid."""
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw)
    except ValueError:
        return default


def main() -> int:
    base_ref = os.environ.get("NLB_BASE_REF", "").strip()
    globs = os.environ.get("NLB_GLOBS", "*.md").split() or ["*.md"]
    ignore = _compile_ignores(_split_list(os.environ.get("NLB_PATHS_IGNORE", "")))
    fail = _env_flag("NLB_FAIL", default=False)
    clause_breaks = _env_flag("NLB_CLAUSE_BREAKS", _DEFAULT_CLAUSE_BREAKS)
    clause_min_length = _env_int("NLB_CLAUSE_MIN_LENGTH", _DEFAULT_CLAUSE_MIN_LENGTH)

    violations, skipped = find_violations(
        base_ref, globs, ignore, clause_breaks, clause_min_length
    )

    if skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(
            f"::warning::Skipping the new-line-breaks check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag pre-existing long lines)."
        )
        return 0

    print(f"Checking for missing semantic line breaks (lines added since {base_ref[:12]})\n")

    if not violations:
        print("No lines missing semantic breaks.")
        return 0

    level = "error" if fail else "warning"
    for violation in violations:
        message = _REASON_MESSAGES[violation.reason]
        print(f"::{level} file={violation.path},line={violation.line}::"
              f"{message}: {violation.preview}")

    print(
        f"\n{len(violations)} line(s) need a semantic break. "
        f"Consider a semantic-break pass (one clause/sentence per line)."
    )
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
