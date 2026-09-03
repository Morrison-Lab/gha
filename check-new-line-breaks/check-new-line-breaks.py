#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""
Flag newly-added Markdown lines that pack more than one sentence/clause onto
a single source line -- a diff-scoped check for semantic line breaks (one
clause/sentence per line).

Design notes:
- **Diff-scoped, always.** Only lines *added* since ``NLB_BASE_REF`` (a PR's
  base SHA) are checked, so a corpus that has already accumulated long lines
  (commonly because markdownlint's MD013 is disabled for exactly this
  reason) never gets reflagged on every unrelated edit.
- **Working-tree-aware scope.** When a *tracked* file the globs match (and
  ``NLB_PATHS_IGNORE`` does not cover) carries a staged or unstaged change,
  the diff is taken against the working tree instead of ``HEAD``, so a line
  added but not yet committed is examined too -- the check is meant to be
  run by hand before a commit, and a clean verdict over zero examined lines
  used to be indistinguishable from a genuine pass (see ``NLB_SCOPE``
  below). Inside CI the tree is always clean, so this has no effect there:
  scope stays committed-only. A brand new *untracked* file never widens
  scope on its own -- plain ``git diff`` cannot show untracked content, so
  letting one flip scope would promise an examination that never happens --
  and is instead named in an explicit warning; stage it (``git add``) to be
  examined for real.
- **No base_ref to diff against, or the diff can't be computed** (e.g. an
  unset base-ref on a push run, or a shallow clone missing the base commit):
  the check is *skipped* with a warning. There is no whole-tree fallback,
  unlike ``check-phi`` -- unlike PHI scanning, this check's entire purpose is
  to avoid ever reflagging pre-existing drift, so a whole-tree scan here
  would defeat the point, not just be less precise.
- **Blocking by default** (``NLB_FAIL`` defaults to true): a long line
  carrying multiple sentences/clauses on one source line fails CI.
- **Two checks, both on by default.** Rule 4 of the SemBr spec (the
  normative MUST: break after a sentence) always applies. A narrow slice of
  rule 5 (the SHOULD: break after an independent clause) applies too, and is
  opt-*out* via ``NLB_CLAUSE_BREAKS=false`` -- see ``has_late_semicolon``
  for why that slice is semicolons only, and why it is gated on line length.
- **The search space is reported.** Every run prints how many added lines
  and files it examined, and under which scope, so a run that examined zero
  lines prints something visibly different from a run that examined
  everything and found nothing.

Configuration (all via environment variables, set by the composite action):
  NLB_BASE_REF      Git ref/SHA to diff against. Empty => skip the check.
  NLB_GLOBS         Space-separated git pathspecs to check (default: '*.md').
  NLB_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  NLB_FAIL          "false" => non-blocking (annotations only); default "true" => blocking.
  NLB_CLAUSE_BREAKS "false" => skip the clause check; default "true" =>
                    also flag long lines carrying a mid-line semicolon.
  NLB_CLAUSE_MIN_LENGTH
                    Minimum *visible* line length before the clause check
                    applies, inclusive (default: 80); markup is stripped
                    first. Ignored when NLB_CLAUSE_BREAKS is false.
  NLB_SCOPE         "auto" (default) => scope from the working tree when a
                    *tracked* file it matches carries a change, else from
                    HEAD; "worktree" => always scope from the working tree;
                    "committed" => always scope from HEAD only, even when
                    the tree is dirty. Line *content* is always read from
                    the working tree regardless of this setting, so forcing
                    "committed" on a dirty tree can desync line numbers --
                    it is meant for reproducing CI's own behavior on a
                    clean tree, not for selectively ignoring uncommitted
                    changes elsewhere. An untracked new file never widens
                    scope on its own (plain `git diff` cannot show it) and
                    is instead named in a warning.
"""

import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import List, NamedTuple, Optional, Set, Tuple

# ── Sentence splitting ──────────────────────────────────────────────────────

# Abbreviations whose trailing period should NOT trigger a sentence split.
#
# These are protected on BOTH sentence-break branches, in their conventional
# case only (`No.`, `Dr.`, `Sec.`, `Fig.`, `e.g.`): a title or label
# abbreviation is essentially never a sentence end, whatever follows it.
# `_ABBREV_RE` runs once, up front, so it reaches both branches -- which is why
# the lowercase forms are handled separately below rather than added here.
_ABBREVS = [
    "e.g", "i.e", "vs", "etc", "Dr", "Mr", "Mrs", "Ms", "Jr", "Sr",
    "Fig", "Eq", "Ref", "Sec", "Ch", "Vol", "pp", "No", "approx",
    "incl", "excl", "ca", "cf", "ibid", "op", "pt", "Dept",
    "al",  # et al.
]


def _abbrev_pattern(forms) -> str:
    """A regex source matching any of `forms` as a whole token before a period."""
    return r"(?<!\w)(" + "|".join(re.escape(a) for a in forms) + r")\."


_ABBREV_RE = re.compile(_abbrev_pattern(_ABBREVS))

# Lowercase abbreviation forms, protected ONLY on the lowercase-follower branch
# (#389) -- applied *after* the uppercase branch has already run (see
# split_sentences). This is the fix for a cross-branch leak caught over three
# review rounds: the disambiguator for a lowercase unit abbreviation is the
# follower's case. `It took 300 ms. The next run ...` (uppercase follower) is a
# genuine sentence boundary and must still split, so this protection must not
# reach the uppercase branch; but `set it to 3 sec. then wait` (lowercase
# follower) is mid-sentence and must not split. Scoping the lowercase forms to
# the lowercase branch is exactly that distinction. `no` is excluded (a
# lowercase `no.` is the English word and should split on either branch), and
# `min`/`hr`/`hrs` are added because bare time units are common in this repo's
# timeout/duration prose and would otherwise false-split before a lowercase
# word. The list is curated, not exhaustive: since the lowercase branch's
# lookbehind only inspects the two trailing characters, ANY unlisted
# abbreviation ending in two lowercase letters -- regardless of its overall case
# (`Inc.`, `Prof.`, `Mon.`, `Jan.`) -- can still false-split before a lowercase
# word, which is a disclosed limitation.
_ABBREV_LOWER = {a.lower() for a in _ABBREVS if a != "No"} | {"min", "hr", "hrs"}
_ABBREV_LOWER_RE = re.compile(
    _abbrev_pattern(sorted(_ABBREV_LOWER, key=len, reverse=True))
)

# Sentence boundary: [.!?] + optional closing chars + whitespace + uppercase/quote.
# The closing-char class includes `*` and `_` so a sentence ending in Markdown
# emphasis (`**Some claim.** Explanation...`, or the `__claim.__` / `_claim._`
# underscore forms) is recognized: the emphasis close sits between the period
# and the whitespace and would otherwise defeat the boundary. A lowercase word
# after the close still blocks this branch's split via the uppercase-or-markup
# lookahead, so mid-sentence emphasis is left intact. Measured 2026-08-03, the
# two characters are worth their place in the class: they raise the
# multi-sentence lines detected across Morrison-Lab/ai-config's Markdown from
# 2837 to 3398 (+19.8%), and across this repo's from 719 to 784 (+9.0%).
_SENT_BREAK_RE = re.compile(r"([.!?][`\"')\]*_]*)\s+(?=[A-Z\"'`*\[])")

# Lowercase-follower boundary (#389). Our prose routinely opens a sentence with
# a bare lowercase package or repo name (`renv`, `serodynamics`, `dplyr`), which
# the uppercase-or-markup lookahead above refuses -- so the check was silent on
# exactly the multi-sentence lines we most often write. This branch accepts a
# following lowercase letter. This comment is the map future widenings will be
# read against, so each attribution below was mutation-verified (remove a guard,
# check which case starts splitting) rather than reasoned about -- three review
# rounds on this PR corrected earlier guesses here.
#
# Two structural guards keep it from over-splitting:
#
#   1. The `(?<=[a-z][a-z])` lookbehind requires two lowercase letters
#      immediately before the terminal punctuation. It is the guard that refuses
#      a single-letter initial (`U.S.`, the `.` follows `S`), a dotted
#      abbreviation (`a.m.`, the `.` follows `.m`), a single-letter token
#      (`option a.`), a digit- or version-ending token (`plan9.`; and `v2.1.` at
#      a clause end, where the `.` DOES have a following space so only the
#      lookbehind blocks it), AND an ellipsis (`wait... foo`): the only dot with
#      a following space is the third, and the two characters before it are both
#      dots, so the lookbehind fails there.
#   2. The terminal `[.!?]` must be *immediately* followed by whitespace -- there
#      is no closing-character class here (unlike the uppercase branch). A
#      character wedged between the punctuation and the space blocks the split,
#      which is what keeps mid-sentence emphasis (`**critical.** yet`) and a
#      quoted or parenthesized fragment (`he said "stop." then`) on one line.
#      A closing class was tried here and removed. The uppercase branch safely
#      carries emphasis and quote closers -- #397 *added* `*`/`_` to its class so
#      a `**bold.**` sentence end is caught -- because its uppercase-follower
#      lookahead still refuses a mid-construct lowercase continuation. This
#      branch's follower is lowercase, so any closer would fire on exactly those
#      mid-construct cases (`"stop." then`, `**critical.** yet`) and re-introduce
#      an over-split; hence no closer class here.
#
# Separately from both guards, an *internal* decimal or version dot (`0.9012`,
# the `.` in `v2.1` between the digits) never even reaches a split attempt: it
# has no following space, so the pre-existing `\s+` requirement fails there.
_SENT_BREAK_LOWER_RE = re.compile(r"(?<=[a-z][a-z])([.!?])\s+(?=[a-z])")

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
    # Protect lowercase abbreviation forms only now, after the uppercase branch
    # has run, so they suppress the lowercase branch below without stopping the
    # uppercase branch from splitting a genuine `... ms. The next ...` boundary.
    protected = _ABBREV_LOWER_RE.sub(lambda m: m.group(1) + _PLACEHOLDER, protected)
    protected = _SENT_BREAK_LOWER_RE.sub(lambda m: m.group(1) + "\n", protected)
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
#
# The code-span pattern backreferences its opening run, so an N-backtick span
# (CommonMark's form for a span that itself contains a backtick) closes on a
# run of the same length rather than on the next backtick. A plain
# `` `[^`]*` `` matches the empty span between the two opening backticks of a
# doubled-backtick span, leaving its contents -- semicolons and all -- in the
# prose.
#
# The bare-URL pattern stops before trailing sentence punctuation, so a `;`
# that ends the clause a URL sits in survives the strip. `\S+` would eat it
# along with the URL and silence a genuine rule 5 break.
_CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1)[\s\S])*?\1")
_LINK_TARGET_RE = re.compile(r"\]\([^)]*\)")
_AUTOLINK_RE = re.compile(r"<https?://[^>\s]*>")
_BARE_URL_RE = re.compile(r"https?://\S*[^\s.,;:!?)\]]")
_ENTITY_RE = re.compile(
    r"&(?:[A-Za-z][A-Za-z0-9]{1,31}|#[0-9]{1,7}|#[xX][0-9A-Fa-f]{1,6});"
)
# One home for each default; action.yml and the reusable workflow declare
# the same values, and a test pins all of them together.
_DEFAULT_FAIL = True
_DEFAULT_CLAUSE_BREAKS = True
_DEFAULT_CLAUSE_MIN_LENGTH = 80


def strip_inline_markup(text: str) -> str:
    """Drop non-prose markup, leaving the prose around it.

    Removes inline code spans, link targets, autolinks, bare URLs, and HTML
    character entities -- every construct that can carry a ``;`` that is not a
    clause boundary, or inflate a line's length without adding visible text.
    The spec sanctions the length half of this directly: rule 13 says a line
    "MAY exceed the maximum line length if necessary, such as to accommodate
    hyperlinks, code elements, or other markup".

    Stripping only ever *removes* characters, so the result is a conservative
    lower bound on a line's visible length: an entity renders as one glyph and
    a code span as its contents, and both are removed outright. Under-counting
    can only suppress a flag, never invent one, which is the safe direction for
    the check.

    Punctuation *adjacent* to a stripped construct is prose, and is kept -- the
    bare-URL pattern deliberately stops short of it, so
    ``see https://example.com/x; the rest`` keeps the ``;`` that a greedy
    ``\\S+`` would have swallowed along with the URL.
    """
    # `]` keeps a bracketed link's visible text attached to its own sentence.
    text = _CODE_SPAN_RE.sub("", text)
    text = _LINK_TARGET_RE.sub("]", text)
    for pattern in (_AUTOLINK_RE, _BARE_URL_RE, _ENTITY_RE):
        text = pattern.sub("", text)
    return text


def has_late_semicolon(text: str, min_length: int = _DEFAULT_CLAUSE_MIN_LENGTH) -> bool:
    """True when ``text`` is long enough and carries a mid-line semicolon.

    That is a *proxy* for the SemBr spec's rule 5, not a test of it, which is
    why the name says what is measured rather than what is inferred. Rule 5
    asks for a break "after an independent clause as punctuated by a comma
    (,), semicolon (;), colon (:), or em dash". The punctuation marks how such
    a clause ends; it is not itself the trigger, and deciding whether a given
    mark ends an *independent* clause needs a parser. Of the four, the
    semicolon is the one whose unparsed hit rate is low enough to be useful:

    - A **comma** is overwhelmingly a list separator, an appositive, or an
      introductory phrase -- rule 6's MAY at most. Measured over
      Morrison-Lab/ai-config's tracked Markdown (22,820 prose lines, already
      conformant), keying on any mid-line ``, ; : --`` flags 50.5% of those
      lines, against 6.1% for the semicolon alone, and 0.7% once the length
      gate below applies. These are a re-measurement taken against the shipped
      code; Morrison-Lab/gha#336 records the original pass, whose figures differ
      because the corpus grew and because the stripping above was widened
      after it was written.
    - A **colon** usually introduces a list or an example, which rule 7
      already breaks before, since the list starts on the next line.
    - A **dash** is usually a paired parenthetical (``X --- Y --- Z``), where
      breaking at the first dash but not the second is wrong.

    The remaining 0.7% still includes hits rule 5 does not cover -- a
    semicolon-delimited list whose items carry their own commas is rule 8's
    MAY -- so what this returns is "worth a second look", which is what this
    check reports.

    The length gate is what separates a genuinely overlong clause chain from
    an ordinary short line that merely contains a semicolon, and it degrades
    gracefully -- a long line with no break opportunity never flags. Its
    default of 80 is the spec's own rule 12, "a maximum line length of 80
    characters is RECOMMENDED": under it, a line needs no break to conform.
    The gate measures the *stripped* length (see ``strip_inline_markup``, and
    rule 13 behind it), so a line that is only long because of a code span, a
    link target, a bare URL, or an autolink does not qualify.
    ``min_length`` is inclusive: a line of exactly that many visible
    characters is checked.

    The semicolon must be interior. One in the last position ends the line
    where a break would go anyway, and one in the first ends nothing. The
    search therefore starts at index 1 rather than filtering afterwards: a
    leading semicolon is skipped over, not treated as the line's answer, so
    it cannot mask a real boundary further along.
    """
    stripped = strip_inline_markup(text).strip()
    if len(stripped) < min_length:
        return False
    semicolon = stripped.find(";", 1)
    return 0 < semicolon < len(stripped) - 1


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
    if clause_breaks and has_late_semicolon(content, clause_min_length):
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
    rules, and HTML comments. (Ported from Morrison-Lab/ai-config's
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


def _status_path(line: str) -> str:
    """Extract the (post-rename) path from one ``git status --porcelain`` line.

    The format is ``XY PATH`` or, for a rename/copy, ``XY PATH -> PATH2``, in
    which case the new path is what matters here. This does not undo git's
    C-style quoting of an exotic filename (a literal quote, backslash, or
    non-ASCII byte); the rest of this module already makes that same
    simplifying assumption when it slices diff header lines.
    """
    rest = line[3:]
    if " -> " in rest:
        rest = rest.split(" -> ", 1)[1]
    return rest.strip().strip('"')


def _has_uncommitted_changes(
    pathspecs: List[str], ignores: List["re.Pattern[str]"]
) -> bool:
    """True when the working tree or index carries a **tracked** change to a
    file the given pathspecs match and ``ignores`` does not cover.

    ``git status --porcelain -uno`` reports staged and unstaged
    modifications to tracked files, which is what "auto" scope needs to
    decide whether to widen the diff. Untracked files are deliberately
    excluded (``-uno``): plain ``git diff`` cannot show untracked content,
    so an untracked file alone must never flip scope to "worktree" -- that
    would promise an examination that then silently does not happen. See
    ``_untracked_matches`` for the warning that covers that gap instead.
    ``ignores`` is applied here too, so an uncommitted edit confined to an
    ignored file does not widen scope for everything else. A status call
    that fails (e.g. not a git repo) is read as "nothing to widen for", the
    same conservative default ``_run_git`` callers elsewhere use.
    """
    out = _run_git(["status", "--porcelain", "-uno", "--", *pathspecs])
    if not out:
        return False
    for line in out.splitlines():
        if not line:
            continue
        if not _ignored(_status_path(line), ignores):
            return True
    return False


def _untracked_matches(
    pathspecs: List[str], ignores: List["re.Pattern[str]"]
) -> List[str]:
    """Untracked files that match ``pathspecs`` and are not covered by
    ``ignores`` -- the set a warning names, since plain ``git diff`` cannot
    show their content even under worktree scope (see
    ``_has_uncommitted_changes``).
    """
    out = _run_git(["status", "--porcelain", "-uall", "--", *pathspecs])
    if not out:
        return []
    matches = []
    for line in out.splitlines():
        if not line.startswith("??"):
            continue
        rel = _status_path(line)
        if not _ignored(rel, ignores):
            matches.append(rel)
    return sorted(matches)


def _merge_base(base_ref: str) -> Optional[str]:
    """The merge base of ``base_ref`` and HEAD, computed explicitly.

    ``git diff A...B`` already resolves to this internally, but both scopes
    below need the same commit, so it is computed once here rather than
    left to two different diff invocations to each resolve on their own --
    which is also what keeps a stale ``base_ref`` from widening the diff:
    the merge base, not ``base_ref`` itself, is what gets diffed against.
    Empty or whitespace-only output (in addition to an outright failure) is
    treated as "could not resolve", since a blank ref satisfies none of the
    diff commands below.
    """
    out = _run_git(["merge-base", base_ref, "HEAD"])
    if out is None:
        return None
    out = out.strip()
    return out or None


def _added_line_numbers(
    base_ref: str, pathspecs: List[str], scope: str = "committed"
) -> Optional[Tuple[dict, "Counter[str]"]]:
    """Return ({file: {new-file line numbers added}}, deleted-line multiset)
    vs the merge-base of base_ref and HEAD, or None if the diff could not be
    computed.

    ``scope`` is ``"committed"`` (diff the merge base against ``HEAD`` --
    CI's own behavior) or ``"worktree"`` (diff the merge base against the
    working tree and index, so an added-but-uncommitted line is examined
    too, the default when the tree carries a change). Either way the merge
    base of ``base_ref`` and ``HEAD`` is resolved once via ``_merge_base``,
    so both scopes share the same anchor and a stale ``base_ref`` cannot
    widen the diff.

    Only the *scope of what counts as added* changes between the two --
    line *content* is always read afterward from the current working tree
    (see ``find_violations``), never from ``HEAD``. That is harmless for
    ``"committed"`` on a clean tree (the two agree), but forcing
    ``"committed"`` on a dirty tree -- via an explicit ``NLB_SCOPE=committed``
    override -- reintroduces the desync this scope machinery exists to fix:
    a line number computed against ``HEAD`` can point at different content
    in the now-edited working tree. The override is meant for reproducing
    exactly what CI would see, which presumes a clean tree; it is not a way
    to selectively ignore uncommitted changes while other uncommitted edits
    are present.

    The deleted-contents set feeds the moved-content exemption (gha#684): an
    added line whose exact text was also deleted somewhere in the same diff is
    relocated content rather than new writing. Collecting it here costs no
    extra git call, and keying the exemption on the diff's own deletions --
    rather than on membership anywhere in the base tree -- is what stops a
    genuinely new line that happens to duplicate untouched base content from
    being silently exempted. It is a multiset, not a set: N deletions of a
    text exempt at most N additions of it, so one deletion cannot launder
    unlimited duplicates (gha#700 round 2).
    """
    merge_base = _merge_base(base_ref)
    if merge_base is None:
        return None
    if scope == "worktree":
        # A single ref with no `--cached`/second ref compares that commit
        # directly to the working tree, folding staged and unstaged changes
        # into one diff -- exactly the population an uncommitted local run
        # needs. A brand-new untracked file still will not appear here:
        # plain `git diff` never shows untracked content (see the module
        # docstring's disclosed limitation).
        diff_args = ["diff", "--unified=0", "--no-color", merge_base, "--", *pathspecs]
    else:
        diff_args = ["diff", "--unified=0", "--no-color", f"{merge_base}..HEAD", "--", *pathspecs]
    diff = _run_git(diff_args)
    if diff is None:
        return None
    result: dict = {}
    deleted: "Counter[str]" = Counter()
    cur_path: Optional[str] = None
    new_lineno = 0
    # Header lines (`--- a/f`, `+++ b/f`) appear only between a `diff` line
    # and that file's first `@@` hunk header, so header-vs-body is decided by
    # position, never by sniffing the line's own prefix: inside a hunk,
    # `--- x` is a deleted line whose content starts with `--`, and `+++ x`
    # an added line whose content starts with `++` (gha#700 round 2).
    in_hunk = False
    for raw in diff.splitlines():
        if raw.startswith("diff "):
            in_hunk = False
            continue
        if not in_hunk and raw.startswith("+++ "):
            target = raw[4:]
            cur_path = None if target == "/dev/null" else target[2:]
            if cur_path is not None:
                result.setdefault(cur_path, set())
            continue
        if raw.startswith("@@"):
            in_hunk = True
            m = _HUNK_RE.match(raw)
            new_lineno = int(m.group(1)) if m else 0
            continue
        if not in_hunk:
            continue
        if raw.startswith("-"):
            deleted[raw[1:]] += 1
            continue
        if raw.startswith("+"):
            if cur_path is not None:
                result[cur_path].add(new_lineno)
            new_lineno += 1
    return result, deleted


class Violation(NamedTuple):
    """One flagged line. ``reason`` names which check flagged it."""

    path: str
    line: int
    preview: str
    reason: str


# The clause message hedges on purpose: the check finds a mid-line semicolon
# past the length gate, and infers a clause boundary from it without parsing
# (see ``has_late_semicolon``). Stating the inference as fact would misreport
# the cases it does not distinguish, such as a semicolon-delimited list.
_REASON_MESSAGES = {
    "sentence": "Line packs more than one sentence",
    "clause": "Long line with a mid-line semicolon; consider a break after the clause",
}


def find_violations(
    base_ref: str,
    globs: List[str],
    ignores: List["re.Pattern[str]"],
    clause_breaks: bool = _DEFAULT_CLAUSE_BREAKS,
    clause_min_length: int = _DEFAULT_CLAUSE_MIN_LENGTH,
    scope_mode: str = "auto",
) -> Tuple[List[Violation], bool]:
    """Return (violations, skipped). violations is empty and skipped is True
    whenever there's no diff to check against -- either base_ref was never
    given (e.g. a push run with no PR to diff against), or a base_ref was
    given but the diff could not be computed (e.g. a shallow clone). Unlike
    check-phi, there is no whole-tree fallback: this check's entire purpose
    is to avoid ever reflagging a corpus's pre-existing long lines, so a
    whole-tree scan here would defeat the point, not just be less precise.

    ``scope_mode`` is ``"auto"`` (widen to the working tree when it carries
    changes to a matched file, else committed-only), ``"worktree"``
    (always widen), or ``"committed"`` (never widen, even when the tree is
    dirty -- CI's own behavior, forced).
    """
    if not base_ref:
        return [], True
    if scope_mode == "worktree":
        scope_kind = "worktree"
    elif scope_mode == "committed":
        scope_kind = "committed"
    else:
        scope_kind = "worktree" if _has_uncommitted_changes(globs, ignores) else "committed"
    scoped = _added_line_numbers(base_ref, globs, scope_kind)
    if scoped is None:
        return [], True
    scope, deleted_contents = scoped
    print(f"Checking for missing semantic line breaks (lines added since {base_ref[:12]})\n")

    untracked = _untracked_matches(globs, ignores)
    if untracked:
        print(
            f"::warning::{len(untracked)} untracked file(s) match the glob "
            "but are not examined (git diff cannot see untracked content; "
            "run `git add` to include them): " + ", ".join(untracked)
        )

    violations: List[Violation] = []
    exempted_moves = 0
    examined_lines = 0
    examined_files = 0
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
        # Only count a file toward the reported search space when it
        # actually contributed an examined line -- a file whose added
        # lines are all non-prose (a heading, a table row) would otherwise
        # print "0 added line(s) across 1 file(s)", which reads like the
        # zero-examined bug this whole feature exists to make visible.
        if target_lines:
            examined_files += 1
            examined_lines += len(target_lines)

        for line_no in sorted(target_lines):
            if line_no < 1 or line_no > len(lines):
                continue
            raw = lines[line_no - 1]
            content = line_content(raw)
            reason = classify_line(content, clause_breaks, clause_min_length)
            if reason is not None:
                preview = content if len(content) <= 80 else content[:77] + "..."
                # Moved-content exemption (gha#684): an added line whose
                # exact text was also deleted somewhere in this same diff is
                # relocated rather than new, so it keeps whatever
                # grandfathering it had. Keyed on the diff's own deletions,
                # never on mere membership in the base tree, so a new line
                # that happens to duplicate untouched base content still
                # flags. The pairing is diff-wide rather than per file-pair,
                # and that is an accepted tradeoff: a deletion in one file
                # exempting an identical addition in another is exactly what
                # a split looks like, and even in the coincidental case the
                # corpus's count of violating lines does not increase.
                if deleted_contents[raw] > 0:
                    deleted_contents[raw] -= 1
                    exempted_moves += 1
                    continue
                violations.append(Violation(rel_path, line_no, preview, reason))
    scope_label = "committed" if scope_kind == "committed" else "working tree"
    print(
        f"Examined {examined_lines} added line(s) across {examined_files} "
        f"file(s) (scope: {scope_label})."
    )
    if exempted_moves:
        print(
            f"Note: {exempted_moves} added line(s) also appear among this "
            "diff's deleted lines (moved, not new) and were not reported."
        )
    return violations, False


# ── Main ─────────────────────────────────────────────────────────────────

def _split_list(value: str) -> List[str]:
    return [tok.strip() for tok in re.split(r"[,\n]", value or "") if tok.strip()]


def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean env var, falling back to ``default`` when unset/empty.

    An unrecognized value warns and falls back to ``default`` rather than
    silently defaulting to false.
    """
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw not in ("true", "false"):
        print(
            f"::warning::{name}={raw!r} is not 'true' or 'false'; "
            f"using default ({default})."
        )
        return default
    return raw == "true"


def _env_int(name: str, default: int) -> int:
    """Read an int env var, falling back to ``default`` when unset or invalid.

    A negative length gate is invalid rather than merely unusual: it would
    admit every line, so it is treated the same as unparseable input.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        print(f"::warning::{name}={raw!r} is not an integer; using {default} instead.")
        return default
    if value < 0:
        print(f"::warning::{name}={raw!r} is negative; using {default} instead.")
        return default
    return value


_SCOPE_CHOICES = ("auto", "worktree", "committed")


def _env_choice(name: str, default: str, choices: Tuple[str, ...]) -> str:
    """Read a string env var restricted to ``choices`` (case-insensitive).

    Falls back to ``default`` when unset, empty, or not a recognized choice,
    warning in the last case the same way ``_env_flag``/``_env_int`` do.
    """
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw not in choices:
        print(
            f"::warning::{name}={raw!r} is not one of {choices}; "
            f"using default ({default!r})."
        )
        return default
    return raw


def main() -> int:
    base_ref = os.environ.get("NLB_BASE_REF", "").strip()
    globs = os.environ.get("NLB_GLOBS", "*.md").split() or ["*.md"]
    ignore = _compile_ignores(_split_list(os.environ.get("NLB_PATHS_IGNORE", "")))
    fail = _env_flag("NLB_FAIL", default=_DEFAULT_FAIL)
    clause_breaks = _env_flag("NLB_CLAUSE_BREAKS", _DEFAULT_CLAUSE_BREAKS)
    clause_min_length = _env_int("NLB_CLAUSE_MIN_LENGTH", _DEFAULT_CLAUSE_MIN_LENGTH)
    scope_mode = _env_choice("NLB_SCOPE", "auto", _SCOPE_CHOICES)

    violations, skipped = find_violations(
        base_ref, globs, ignore, clause_breaks, clause_min_length, scope_mode
    )

    if skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        print(
            f"::warning::Skipping the new-line-breaks check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag pre-existing long lines)."
        )
        return 0

    if not violations:
        print("No lines missing semantic breaks.")
        return 0

    for violation in violations:
        message = _REASON_MESSAGES[violation.reason]
        print(f"::error file={violation.path},line={violation.line}::"
              f"{message}: {violation.preview}")

    print(
        f"\n{len(violations)} line(s) need a semantic break. "
        f"Consider a semantic-break pass (one clause/sentence per line)."
    )
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
