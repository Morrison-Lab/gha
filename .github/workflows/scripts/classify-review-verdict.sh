#!/usr/bin/env bash
# Classifies a Claude Code Review assistant verdict text as clean vs not clean.
#
# Usage: classify-review-verdict.sh <review-text-file>
#
# Reads the extracted review assistant text (from check-review-execution.sh or
# review.txt in the review payload artifact) and outputs:
#   clean=true|false
#   verdict=<slug>
# to $GITHUB_OUTPUT (if set) and stdout.
#
# A verdict is clean (clean=true) when the verdict section states an
# affirmative clean conclusion ("Ready for merge", "Clean", "Approved",
# "No findings") and does NOT state an unnegated rejection or blocking status
# ("Needs more work", "Changes requested", "Blocked", "Impasse", "Rejected").
#
# A well-formed structured "review-data" payload (an HTML comment carrying a
# schema_version and a verdict of CLEAN or NOT_CLEAN) is classified from that
# field directly and takes precedence over the prose scan (gha#845). Any
# other body -- no such payload, malformed JSON, or a verdict value outside
# CLEAN/NOT_CLEAN -- falls back to the prose scan unchanged.
#
# Offline tests live in tests/run-classify-review-verdict-tests.sh.
set -euo pipefail

REVIEW_FILE="${1:?usage: classify-review-verdict.sh <review-text-file>}"
GITHUB_OUTPUT="${GITHUB_OUTPUT:-/dev/null}"

python3 - "$REVIEW_FILE" "$GITHUB_OUTPUT" << 'EOF'
import json
import os
import re
import sys

review_file = sys.argv[1]
output_file = sys.argv[2]

def record(clean, slug):
    if output_file and output_file != "/dev/null" and os.path.exists(output_file):
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(f"clean={clean}\nverdict={slug}\n")
    print(f"clean={clean}\nverdict={slug}")
    sys.exit(0)

if not os.path.isfile(review_file):
    record("false", "missing-file")

try:
    with open(review_file, "r", encoding="utf-8", errors="replace") as f:
        # NUL bytes are replaced with a SPACE here, before anything downstream
        # can rely on their absence (gha#827 review).
        #
        # strip_emphasis protects an intra-word underscore by swapping it for a
        # NUL sentinel and swapping it back afterwards. That final replace
        # cannot tell its own sentinel from a NUL that was already in the text,
        # so a real one became an underscore, merged two words into a single
        # \w-class token, and stopped a genuine rejection phrase from matching:
        # "needs<NUL>more work" after the verdict heading scored
        # ready-for-merge instead of needs-more-work. That is the false-CLEAN
        # direction, which bypasses require-clean-verdict on a review that said
        # the opposite.
        #
        # An earlier revision of the sentinel comment asserted NUL was "stripped
        # from the review text by the time it reaches here". That was never
        # checked and is false: check-review-execution.sh extracts the text with
        # `jq -r`, which passes a NUL straight through, and errors="replace"
        # does not touch it either, since NUL is a valid single-byte UTF-8
        # codepoint rather than an invalid sequence. Verified:
        #   python3 -c "import json; print(json.dumps({'a':'foo\x00bar'}))" \
        #     | jq -r '.a' | od -c   ->   f o o \0 b a r
        #
        # A SPACE rather than deletion, for the reason the placeholder above is
        # a word rather than nothing: deleting glues the neighbours together
        # ("needs<NUL>more" -> "needsmore") and reproduces the same class of
        # missed match it is meant to fix.
        text = f.read().replace("\x00", " ")
except Exception:
    record("false", "missing-file")

if not text.strip():
    record("false", "no-output")

# --- Shared fence/blockquote region tracking (gha#845 review, finding 1) ---
#
# Both the review-data payload extraction below and strip_machine_payloads
# (further down) need to know whether a given line sits inside an open
# fenced code block. Keeping that state machine in exactly one place is what
# makes the two agree -- a payload only strip_machine_payloads considered
# fenced, while the payload scan above it did not (or vice versa), is
# exactly how a blockquoted or fenced stale/adversarial payload got trusted
# as the live verdict: a review whose prose verdict was "Needs more work"
# and which blockquoted (or fenced) an older CLEAN payload was classified
# clean=true, because the payload scan searched the raw, unstripped text.
# CommonMark only recognizes a fence indented 0-3 spaces; 4+ spaces or a tab
# is an INDENTED code block instead, a distinct construct these two regexes
# used to ignore entirely. That is a payload-trust gap rather than a
# rendering nuance here (gha#845 second review, finding 3): a
# `<!-- review-data: ... -->` line sitting inside a tab- or 4-space-indented
# fence was tracked as neither fenced nor blockquoted, so the payload scan
# below trusted it as the live verdict even while the prose verdict said
# otherwise. The fix widens both patterns to ALSO recognize a fence marker
# preceded by a tab or by any number of spaces (not only 0-3), so a deeply
# indented ``` fence is tracked the same as a top-level one. That is
# deliberately broader than CommonMark's own rule -- erring toward treating
# more content as fenced only ever REMOVES trust from a payload, never adds
# it, which is the safe direction for a fast path whose whole point is
# deciding what to trust.
_FENCE_OPEN_RE = re.compile(r'[ \t]*(`{3,}|~{3,})')
_FENCE_CLOSE_RE = re.compile(r'[ \t]*(`{3,}|~{3,})[ \t]*$')
_BLOCKQUOTE_RE = re.compile(r'[ \t]*>')
# A line indented by a tab or 4+ spaces is CommonMark's plain indented code
# block, with no fence markers at all -- so a `<!-- review-data: ... -->`
# line indented that way was previously tracked as ordinary unfenced,
# unquoted text and trusted like any other line. Simplest fix (gha#845
# second review, finding 3): exclude such a line from the payload candidate
# text outright, rather than modeling list-continuation indentation, which
# this scan has no other reason to understand.
_INDENTED_RE = re.compile(r'^(?:\t| {4,})')


def _open_fence(line):
    """Return (char, length) if `line` opens a new fenced code block, else None."""
    m = _FENCE_OPEN_RE.match(line)
    if not m:
        return None
    return m.group(1)[0], len(m.group(1))


def _fence_closes(line, fence_char, fence_len):
    """Whether `line` closes a fence opened with `fence_char`/`fence_len`.

    A fence closes only on a run of the same character at least as long as
    the opener with nothing but whitespace after it (matching
    strip-non-invoking-markup.sh's rule, and CommonMark's).
    """
    m = _FENCE_CLOSE_RE.match(line)
    return bool(m and m.group(1)[0] == fence_char and len(m.group(1)) >= fence_len)


def _iter_fence_and_quote_state(lines):
    """Yield (line, in_fence, quoted) for each source line.

    in_fence tracks the SAME top-level fence state strip_machine_payloads
    uses below, via the shared _open_fence/_fence_closes helpers, so the two
    cannot disagree about what is fenced. quoted is True only for a
    non-fenced blockquote line (a leading '>' after optional whitespace);
    CommonMark does not treat a '>' inside a fence as a blockquote marker,
    so quoted is never reported while in_fence is True.
    """
    fence_char = ""
    fence_len = 0
    for raw in lines:
        line = raw
        if fence_char:
            if _fence_closes(line, fence_char, fence_len):
                fence_char = ""
                fence_len = 0
            yield line, True, False
            continue
        opened = _open_fence(line)
        if opened:
            fence_char, fence_len = opened
            yield line, True, False
            continue
        yield line, False, bool(_BLOCKQUOTE_RE.match(line))


# gha#845: the structured review-data payload states its own verdict, and a
# machine reader should trust that field rather than re-derive it from prose.
# This runs BEFORE strip_machine_payloads (below) discards the payload, and
# before the prose scan, because the payload is the more authoritative
# source when both are present -- a body whose prose says "Ready for merge"
# but whose payload says NOT_CLEAN (a stale caption on a re-run, for
# instance) is classified from the payload, not the prose.
#
# The payload is read only from lines that are neither fenced nor
# blockquoted (gha#845 review, finding 1): a `<!-- review-data: ... -->`
# that appears only inside a `> ...` blockquote or a fenced code block is
# someone QUOTING an earlier (possibly stale) payload, not stating the live
# one -- the same reasoning strip_machine_payloads's own comment already
# gives for why quoted/fenced prose isn't a verdict statement. Blockquoted
# and fenced lines are blanked before the marker search, reusing the fence
# tracking strip_machine_payloads uses below, so the two cannot disagree
# about what counts as fenced.
_payload_candidate_lines = [
    ("" if (in_fence or quoted or _INDENTED_RE.match(line)) else line)
    for line, in_fence, quoted in _iter_fence_and_quote_state(text.splitlines())
]
_payload_candidate_text = "\n".join(_payload_candidate_lines)

# Only the LAST such comment counts, matching the prose scan's own
# last-match-wins rule elsewhere in this file. Any block that fails to parse
# as JSON, lacks a schema_version key, or carries a verdict outside
# CLEAN/NOT_CLEAN falls through to the prose scan unchanged -- this is a
# fast path for a well-formed payload, not a replacement for the fallback.
#
# The JSON body is located with json.JSONDecoder().raw_decode rather than a
# regex (gha#845 review, finding 2): a non-greedy `(.*?)\s*-->` regex cannot
# tell a "-->" INSIDE a JSON string value from the marker's own closing
# delimiter, and truncates at the first one it finds -- a NOT_CLEAN payload
# whose "note" field happened to contain the three characters "-->" produced
# invalid JSON, silently fell back to the prose scan, and could misclassify
# a review the payload had already marked NOT_CLEAN as ready for merge.
# raw_decode parses exactly one JSON value starting at a given index and
# does not care what a string's contents look like, so it has no such blind
# spot.
_payload_marker_re = re.compile(r'<!--\s*review-data:\s*', re.IGNORECASE)
_payload_markers = list(_payload_marker_re.finditer(_payload_candidate_text))
payload = None
if _payload_markers:
    _decoder = json.JSONDecoder()
    _start = _payload_markers[-1].end()
    try:
        _decoded, _end = _decoder.raw_decode(_payload_candidate_text, _start)
    except (ValueError, TypeError):
        _decoded = None
    else:
        # Require that only whitespace and the comment's own closing "-->"
        # follow the parsed object -- anything else means the marker wasn't
        # actually followed by a single well-formed `{...} -->` comment, and
        # the object that happened to parse starting at that offset isn't
        # trustworthy just because it parsed.
        if re.match(r'\s*-->', _payload_candidate_text[_end:]):
            payload = _decoded
if isinstance(payload, dict) and "schema_version" in payload:
    verdict_field = payload.get("verdict")
    if isinstance(verdict_field, str):
        payload_verdict = verdict_field.strip().upper()
        if payload_verdict == "CLEAN":
            # A CLEAN verdict with actual findings attached is internally
            # inconsistent, so it is not trustworthy as a fast path -- fall
            # through to the prose scan rather than inventing a NOT_CLEAN
            # this code never observed (gha#845 review, finding 3).
            # NOT_CLEAN is trusted regardless of findings: a rejection with
            # no listed findings is still a rejection.
            findings = payload.get("findings")
            findings_is_empty = findings is None or (
                isinstance(findings, list) and len(findings) == 0
            )
            if findings_is_empty:
                record("true", "ready-for-merge")
            # else: falls through to the prose scan.
        elif payload_verdict == "NOT_CLEAN":
            record("false", "needs-more-work")
        # Any other verdict value falls through to the prose scan.

# Machine payloads and quoted blocks are not verdict statements (gha#819).
# This repo's reviews emit a structured review-data block AFTER the verdict
# heading -- once as an HTML comment, once in a ```json fence -- and the scan
# below is last-match-wins, so one finding word in that JSON prose overrode
# the stated verdict. Measured on gha#811: `"holistic_assessment": "The
# gh-pages concurrency-deadlock audit ..."` scored an approving review
# `impasse`, and require-clean-verdict failed the job on it. A PR whose
# SUBJECT is a blocked or deadlocked condition cannot avoid that by
# rewording, which is why these regions are excluded structurally rather than
# the keyword list being narrowed.
#
# EVERY fenced block is excluded, not only the two payload spellings this
# repo emits, and the stripping covers the whole document rather than just
# the part after the heading -- which is what stops a fenced heading from
# winning last_idx below. That is deliberate and it cuts both ways: a
# reviewer who states an approving verdict and then puts a genuinely blocking
# note inside a fence is scored clean. The alternative -- matching on
# `<!-- review-data:` and ```json specifically -- would classify from any
# other fenced content, which is how a review that merely QUOTES a verdict
# block (as a review of this very change does) scores from the quotation.
# Quoted text is the commoner shape by far, so it is the one worth being
# wrong about.
#
# Stripping happens BEFORE the verdict-heading scan, not after it. Scanning
# first lets a heading inside a fence win `last_idx`, and classification then
# starts mid-payload (gha#819 review, finding 1).
#
# Comment SPANS are excised rather than whole lines, so `**Ready for merge.**
# <!-- run 123 -->` keeps its verdict; dropping the line lost it (finding 2).
# The scan repeats within a line, so a second opener after a closed span is
# still seen (finding 3).
#
# Fence tracking takes its closing rule from strip-non-invoking-markup.sh: a
# fence closes only on a run of the same character at least as long as the
# opener with nothing but whitespace after it, and an unclosed fence runs to
# the end of the text. It covers top-level fences only; that sibling also
# handles indented code blocks, and a fence nested four or more columns deep
# inside a list is not recognized here (round 2, finding 4).
def strip_machine_payloads(src):
    out = []
    fence_char = ""
    fence_len = 0
    in_comment = False
    for raw in src:
        line = raw
        if in_comment:
            idx = line.find("-->")
            if idx == -1:
                out.append("")
                continue
            line = line[idx + 3:]
            in_comment = False
        if fence_char:
            # Reuses the same _fence_closes helper the review-data payload
            # scan above uses, so the two agree on where a fence closes
            # (gha#845 review, finding 1).
            if _fence_closes(line, fence_char, fence_len):
                fence_char = ""
                fence_len = 0
            out.append("")
            continue
        # The fence opener is tested before the comment scan, and no
        # `in_comment` short-circuit sits between them. An earlier draft had
        # that short-circuit, so a `<!--` on the opener line skipped the fence
        # check entirely and the fence body was classified (gha#819 review
        # round 2, finding 1). Removing it is what fixes that; the ordering
        # additionally keeps `<!-- x -->```json` from opening a fence, which
        # CommonMark does not treat as one either, since a fence must start
        # its line.
        #
        # Reuses the same _open_fence helper the review-data payload scan
        # above uses (gha#845 review, finding 1).
        opened = _open_fence(line)
        if opened:
            fence_char, fence_len = opened
            out.append("")
            continue
        while True:
            opener = line.find("<!--")
            if opener == -1:
                break
            # From opener + 2, so the empty comments CommonMark allows,
            # `<!-->` and `<!--->`, terminate here too; treating them as
            # unterminated swallowed the rest of the review and could score a
            # later finding word clean (round 2, finding 3).
            closer = line.find("-->", opener + 2)
            if closer == -1:
                line = line[:opener]
                in_comment = True
                break
            # Joined with no separator, as a renderer joins them. Inserting a
            # space fabricates a word boundary, and that error direction can
            # invent a match rather than only lose one (round 2, finding 2).
            line = line[:opener] + line[closer + 3:]
        out.append(line)
    return out

# Inline code spans are quoted strings, not verdict statements (gha#827).
#
# strip_emphasis below deletes the tick CHARACTERS and classifies the words
# inside, so `NOT_CLEAN` -- a backticked identifier naming an instrument's
# output -- became the two words "NOT CLEAN" and matched the negated-positive
# pattern as a rejection. Because the scan is last-match-wins, that line
# outranked the `**Ready for merge**` line above it and flipped an approving
# review to needs-more-work (measured on Morrison-Lab/ai-config#3154, run
# 33832648873).
#
# This is the inline-code sibling of gha#819's fenced-block exclusion.
#
# (An earlier revision of this comment claimed run-claude-review-attempt's
# brief instructs the reviewer to wrap quoted verdict words in single
# backticks. That claim came from gha#827's issue body and does not hold:
# `grep -rn -i backtick .github/actions/run-claude-review-attempt/` returns
# nothing. The fix stands on its own -- quoting an identifier in backticks is
# ordinary Markdown, not a behaviour the brief induces -- but the false
# citation is removed rather than repeated.)
#
# The span is replaced by a placeholder word rather than deleted. Deleting it
# closes its neighbours up, and that direction can INVENT a match rather than
# only lose one: `no `x` findings` would become "no findings", which the
# negated-negative pattern reads as an affirmative clean statement. The
# placeholder blocks that, because noun_neg_gap_pattern admits only a fixed
# list of adjectives and "codespan" is not among them. It must also be a word
# no pattern here matches, which rules out the obvious "code".
#
# The placeholder is an ORDINARY word to pos_gap_pattern, which is deliberate
# and has one known cost. That pattern excludes "and", "but" and "whereas" as
# gap fillers, so a span whose entire content is one of those three words
# blocks a negated-positive match while unblanked and admits it once blanked:
# "not `and` ready for merge" scores needs-more-work where the unbackticked
# "not and ready for merge" scores ready-for-merge. Measured (gha#827 review).
#
# That is accepted rather than fixed, because both directions were weighed and
# this one errs safely. Choosing a placeholder from the excluded set would
# block the gap generally, so "not `really` clean" would stop matching and a
# genuine rejection would score CLEAN -- a PR merged over a rejection. The
# current choice errs the other way, toward a false rejection, which costs a
# re-review. The trigger is also an artificial sentence: any other span content
# behaves identically blanked or not.
#
# Newlines inside a span are preserved so the line COUNT does not change, which
# keeps this function's output line-aligned with its input.
#
# That is defensive rather than load-bearing, and saying so is the honest
# reading: no test distinguishes it. Three fixtures were tried against a
# mutation that drops the newlines and all three scored identically, because
# the result is re-split immediately below, so last_idx and the content slice
# stay self-consistent whatever the line count is. Keep the preservation --
# alignment with the source is worth having if anything here ever reports a
# line number -- but do not claim a verdict depends on it.
#
# Closing follows CommonMark rather than `\`[^\`]*\``: a span opens on a run of
# N backticks and closes only on a run of exactly N. The naive pattern matches
# the empty span between the two opening ticks of a ``..`` span and leaks the
# contents through, which is the same bug this repo already records for
# check-new-line-breaks' strip_inline_markup. An unclosed run is left alone.
def _scan_code_spans(text):
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "`":
            out.append(text[i])
            i += 1
            continue
        j = i
        while j < n and text[j] == "`":
            j += 1
        run = j - i
        close = -1
        k = j
        while k < n:
            if text[k] == "`":
                m = k
                while m < n and text[m] == "`":
                    m += 1
                if m - k == run:
                    close = k
                    break
                k = m
            else:
                k += 1
        if close == -1:
            out.append(text[i:j])
            i = j
            continue
        out.append(" codespan ")
        out.append("\n" * text[j:close].count("\n"))
        i = close + run
    return "".join(out).split("\n")

# A code span is INLINE content, so it cannot cross a blank line: CommonMark
# ends the containing paragraph there. Scanning the whole document as one flat
# string ignores that, and the consequence is a regression rather than a
# nicety -- two unrelated stray backticks in different paragraphs pair into a
# "span" that blanks everything between them, the real `### Verdict` heading
# included, scoring an approving review no-verdict.
#
# Reproduced during review of this change: a body reading "A note about the
# `foo flag." / blank / "### Verdict" / blank / "**Ready for merge**" / blank /
# "See the `bar setting." scored clean=false verdict=no-verdict before this
# split and clean=true verdict=ready-for-merge after it.
#
# Blank lines are emitted unchanged rather than fed to the scanner, so the line
# count is preserved here for the same reason it is preserved inside a span.
def strip_code_spans(src_lines):
    out_lines = []
    block = []

    def flush():
        if block:
            out_lines.extend(_scan_code_spans("\n".join(block)))
            del block[:]

    for line in src_lines:
        if line.strip():
            block.append(line)
        else:
            flush()
            out_lines.append(line)
    flush()
    return out_lines

lines = strip_code_spans(strip_machine_payloads(text.strip().splitlines()))
header_regex = re.compile(
    r'^[ \t]*#{1,6}[ \t]+(\*\*)?verdict'
    r'|^[ \t>*_#-]*(\*\*verdict:?\*\*|\*\*verdict\*\*|verdict:)'
    r'|^[ \t>*_#-]*verdict[: \t*_-]*$',
    re.IGNORECASE
)

last_idx = -1
for i, line in enumerate(lines):
    if header_regex.search(line):
        last_idx = i

if last_idx == -1:
    record("false", "no-verdict")

verdict_lines = lines[last_idx:]

# gha#845 second review, finding 2: verdict_lines[0] is always the line
# header_regex matched -- the heading itself. The skip-check below already
# drops it when it is heading-only ("### Verdict" or "**Verdict:**" with
# nothing else), leaving the NEXT line as content_lines[0]. But a heading and
# its verdict written on the SAME line ("### Verdict: No action -- trivial",
# "**Verdict:** No action -- automated, trivial PR ...") is not heading-only,
# so it used to survive into content_lines[0] verbatim, WITH the "Verdict:"
# label still attached at the front. That label defeats the line-anchored
# no_action_anchor check below, which requires the verdict content itself to
# start the line -- and clean_kw carries no bare "no action" alternative to
# fall back on (gha#845's first review already removed it as unanchored).
# The fix strips a leading heading/label prefix from verdict_lines[0]
# specifically, so only the REMAINDER after "Verdict:" becomes
# content_lines[0], matching the heading-only case where that remainder was
# always on its own line.
_heading_prefix_re = re.compile(
    r'^[ \t>*_#-]*(?:\*\*)?verdict:?(?:\*\*)?[: \t*_-]*',
    re.IGNORECASE
)

content_lines = []
for _vl_idx, line in enumerate(verdict_lines):
    if re.search(r'^[ \t>*_#-]*verdict[: \t*_-]*$', line, re.IGNORECASE) or \
       re.search(r'^[ \t]*#{1,6}[ \t]+(\*\*)?verdict[: \t*_-]*$', line, re.IGNORECASE):
        continue
    stripped = line.strip()
    if not stripped:
        continue
    if _vl_idx == 0:
        remainder = _heading_prefix_re.sub('', stripped, count=1).strip()
        if remainder:
            content_lines.append(remainder)
        continue
    content_lines.append(stripped)

if not content_lines:
    content_lines = [l.strip() for l in verdict_lines if l.strip()]

if not content_lines:
    record("false", "no-verdict")

def strip_emphasis(s):
    # Strip markdown bold, italic, strikethrough, code ticks so inline styling around words is normalized
    #
    # An underscore BETWEEN two alphanumerics is part of an identifier, not
    # emphasis around a word: NOT_CLEAN is one token, and splitting it into
    # "NOT CLEAN" is what let a bare (unbackticked) mention of an instrument's
    # output read as a rejection (gha#827). Markdown does not treat an
    # intra-word underscore as emphasis either, so this matches the renderer.
    #
    # Protecting it is enough on its own -- no separate guard is needed --
    # because `_` is a word character to `re`, so `\bnot\b` cannot match
    # inside the surviving NOT_CLEAN.
    #
    # The sentinel is NUL, which is safe here only because the read at the top
    # of this script replaces every NUL in the input with a space FIRST. A
    # printable stand-in would risk colliding with real content instead.
    #
    # That ordering is load-bearing rather than incidental. The replace below
    # cannot distinguish this sentinel from a NUL that was already in the text,
    # so without the read-time scrub a real one became an underscore and merged
    # two words of a genuine rejection into one token, scoring it clean
    # (gha#827 review). An earlier revision of this comment asserted NUL was
    # already stripped upstream; it is not, and the scrub is what makes the
    # claim true rather than a hope.
    s = re.sub(r'(?<=[A-Za-z0-9])_(?=[A-Za-z0-9])', '\x00', s)
    return re.sub(r'[*_~`]+', ' ', s).replace('\x00', '_')

def expand_contractions(s):
    contractions = [
        (r"\bisn['’]?t\b", "is not"),
        (r"\bwasn['’]?t\b", "was not"),
        (r"\baren['’]?t\b", "are not"),
        (r"\bweren['’]?t\b", "were not"),
        (r"\bdoesn['’]?t\b", "does not"),
        (r"\bdon['’]?t\b", "do not"),
        (r"\bdidn['’]?t\b", "did not"),
        (r"\bcan['’]?t\b", "can not"),
        (r"\bcannot\b", "can not"),
        (r"\bcouldn['’]?t\b", "could not"),
        (r"\bwon['’]?t\b", "will not"),
        (r"\bwouldn['’]?t\b", "would not"),
        (r"\bshouldn['’]?t\b", "should not"),
        (r"\bhasn['’]?t\b", "has not"),
        (r"\bhaven['’]?t\b", "have not"),
        (r"\bhadn['’]?t\b", "had not"),
        (r"\bain['’]?t\b", "is not"),
    ]
    for pattern, replacement in contractions:
        s = re.sub(pattern, replacement, s, flags=re.IGNORECASE)
    return s

aside_pattern = r'\s*[-,\(:;—–"\'«»“”‘’\[\]{}]\s*[^.!?\n]+?\s*[-,\):;—–"\'«»“”‘’\[\]{}]?\s*'
pos_gap_pattern = rf'(?:{aside_pattern}|(?:\s+yet)?(?:\s+(?!(?:and|but|whereas)\b)\w+)*\s*)'
noun_neg_gap_pattern = r'(?:\s+(?:actionable|blocking|open|remaining|new|unresolved|further|additional|other))*\s*'
pred_neg_gap_pattern = rf'(?:{aside_pattern}|(?:\s+(?:longer|currently|strictly|really|necessarily|at\s+present))*\s*)'

pos_neg_prefix = rf'\b(not|never|un-?|non-?|no\s+longer|without)\b{pos_gap_pattern}'
noun_neg_prefix = rf'\b(no|zero|0|without)\b{noun_neg_gap_pattern}'
pred_neg_prefix = rf'\b(no\s+longer|not|never|un-?|non-?)\b{pred_neg_gap_pattern}'
# The leading \b is load-bearing (gha#827 review). pos_gap_pattern ends in
# `\s*`, and its word repetition is `\w+`, so without a boundary here the regex
# backtracks INSIDE a word: "already" splits into the gap word "al" plus the
# target "ready", and any sentence of the form "... not ... already ..." after
# the verdict heading scored a rejection. Measured against origin/main, a body
# stating **Ready for merge** and then "The base was not already current, so I
# updated it." classified needs-more-work.
#
# This is a distinct root cause from the code-span blanking above -- it needs no
# backticks and no underscore -- but it is the same symptom, so a review body
# carrying both was still misclassified once the span fix alone was applied.
positive_targets = r'\b(ready\s+(?:for|to)\s+merge|ready(?!\s+(?:for|to)\b)|approved|clean|lgtm)'
noun_negative_targets = r'(findings|blocking\s+findings|blocking\s+issues|actionable\s+findings|blockers?|changes\s+(?:requested|required))'
pred_negative_targets = r'(needs\s+more\s+work|needs\s+work|blocked|impasse|deadlock|rejected|unapproved)'

negated_positive_phrases = re.compile(
    rf'{pos_neg_prefix}{positive_targets}\b',
    re.IGNORECASE
)
negated_negative_phrases = re.compile(
    rf'(?:{noun_neg_prefix}{noun_negative_targets}|{pred_neg_prefix}{pred_negative_targets})\b',
    re.IGNORECASE
)
non_clean_kw = re.compile(
    r'\b(needs\s+more\s+work|needs\s+work|changes\s+requested|changes\s+required|blocked|impasse|deadlock|rejected|unapproved)\b',
    re.IGNORECASE
)
clean_kw = re.compile(
    r'\b(ready\s+for\s+merge|ready\s+to\s+merge|approved|lgtm|no\s+findings|no\s+blocking\s+issues|no\s+blocking\s+findings|no\s+actionable\s+findings)\b|\bclean\b(?!\s+up\b)|\bpassed\b',
    re.IGNORECASE
)
# "no action" and "does not need (code) review" used to sit inside clean_kw
# above, scanned against EVERY content line like any other keyword. Both
# read fine in the repo's triage-exemption template
# ("**No action -- automated, trivial PR that does not need code
# review**"), but a bare, unanchored "no action" also matches ordinary
# prose that has nothing to do with a verdict -- "No action has been taken
# since the last round" -- and because the scan is last-line-wins, that
# sentence appearing on a line AFTER a real "Changes requested" flipped the
# whole review clean=true (gha#845 review, finding 4).
#
# "does not need (code) review" is removed outright rather than anchored:
# unlike "no action", it has no fixed position in the triage template ("...
# that does not need code review"), so no anchor rules out "does not need
# review from a human once that's fixed" appearing as ordinary prose after
# a real rejection.
#
# "no action" is kept, but ONLY as a check against the verdict's own first
# content line (see first_nonempty_idx below) rather than as a mid-line
# alternative scanned against every line. That is the triage template's
# actual shape: the exemption is STATED as the verdict, not mentioned
# somewhere in the explanation below it. Restricting the anchor to the
# verdict line is what lets "No action has been taken since the last round"
# (a later, unrelated sentence) fail to match while "**No action --
# automated, trivial PR ...**" (the verdict line itself) still does.
#
# Being the FIRST word of the verdict line is necessary but not sufficient
# (gha#845 second review, finding 1): "No action was taken on the flaky
# test, but there are still open issues to resolve here." also starts with
# "no action", reads as ordinary triage prose rather than the clean
# exemption, and scored clean=true. The template's actual shape has "no
# action" stating the WHOLE verdict, with nothing left open after it -- so
# the anchor now requires the rest of that line to carry no still-open
# vocabulary (still_open_after_no_action) and no rejection keyword
# (non_clean_kw / negated_positive_phrases). Any of those firing means the
# line merely happens to start with the words "no action" while describing
# unresolved work, so the anchor does not classify and the normal keyword
# scan decides the line on its own -- which may still be "unrecognized" if
# nothing else in it matches either.
no_action_anchor = re.compile(
    r'^\s*no\s+action(?:\s+(?:needed|required|necessary))?\b',
    re.IGNORECASE
)
still_open_after_no_action = re.compile(
    r'\b(?:still|remain\w*|open|unresolved|outstanding|but|however|not\s+yet|pending)\b',
    re.IGNORECASE
)
footer_regex = re.compile(
    r'^[ \t>*_#-]*(\*\*)?(stopping\s+point|reviewed\s+commit|posted\s+by)\b',
    re.IGNORECASE
)

# gha#845 second review, finding 4: an emphasis-only first content line
# ("**" with nothing else) hides the real verdict from the anchor check
# above, which used to fire on content_lines[0] specifically regardless of
# what survives strip_emphasis. "### Verdict\n\n**\n\nNo action needed --
# automated, trivial PR." puts the actual verdict on content_lines[1], but
# the old code checked content_lines[0] ("**", which strips to nothing) and
# never looked further. The anchor now runs on the first content line whose
# text is non-empty AFTER strip_emphasis, found here rather than assumed to
# be index 0.
first_nonempty_idx = None
for _cl_idx, _cl in enumerate(content_lines):
    if strip_emphasis(_cl).strip():
        first_nonempty_idx = _cl_idx
        break

# Single ordered scan in document order: last verdict statement wins
last_verdict = None

for line_index, line in enumerate(content_lines):
    if footer_regex.search(line):
        continue

    norm_line = expand_contractions(strip_emphasis(line))
    neg_pos_spans = []
    neg_neg_spans = []
    line_matches = []

    if line_index == first_nonempty_idx:
        m = no_action_anchor.match(norm_line)
        if m:
            rest = norm_line[m.end():]
            if not still_open_after_no_action.search(rest) and \
               not non_clean_kw.search(norm_line) and \
               not negated_positive_phrases.search(norm_line):
                line_matches.append((m.start(), "true", "ready-for-merge"))

    for m in negated_positive_phrases.finditer(norm_line):
        neg_pos_spans.append((m.start(), m.end()))
        matched_text = m.group(0).lower()
        slug = 'needs-more-work'
        if 'approved' in matched_text:
            slug = 'rejected'
        line_matches.append((m.start(), "false", slug))

    for m in negated_negative_phrases.finditer(norm_line):
        neg_neg_spans.append((m.start(), m.end()))
        line_matches.append((m.start(), "true", "ready-for-merge"))

    for m in non_clean_kw.finditer(norm_line):
        if any(start <= m.start() < end for start, end in neg_neg_spans):
            continue
        text_matched = m.group(1).lower()
        slug = 'needs-more-work'
        if re.search(r'\bchanges\s+(?:requested|required)\b', text_matched):
            slug = 'changes-requested'
        elif re.search(r'\bblocked\b', text_matched):
            slug = 'blocked'
        elif re.search(r'\b(impasse|deadlock)\b', text_matched):
            slug = 'impasse'
        elif re.search(r'\b(rejected|unapproved)\b', text_matched):
            slug = 'rejected'
        line_matches.append((m.start(), "false", slug))

    for m in clean_kw.finditer(norm_line):
        if any(start <= m.start() < end for start, end in neg_pos_spans):
            continue
        if any(start <= m.start() < end for start, end in neg_neg_spans):
            continue
        text_matched = m.group(0).lower()
        if text_matched == 'passed':
            # Ignore incidental test/CI/suite passed occurrences
            prefix = norm_line[:m.start()]
            if re.search(r'\b(?:test|tests|suite|check|checks|ci|run|step|pipeline|build|workflow)\s*$', prefix, re.IGNORECASE):
                continue
        slug = 'ready-for-merge'
        if re.search(r'\bapproved\b', text_matched):
            slug = 'approved'
        elif re.search(r'\bclean\b', text_matched):
            slug = 'clean'
        line_matches.append((m.start(), "true", slug))

    if line_matches:
        line_matches.sort(key=lambda x: x[0])
        _, clean_val, slug_val = line_matches[-1]
        last_verdict = (clean_val, slug_val)

if last_verdict is not None:
    record(*last_verdict)

record("false", "unrecognized")
EOF

