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
# Offline tests live in tests/run-classify-review-verdict-tests.sh.
set -euo pipefail

REVIEW_FILE="${1:?usage: classify-review-verdict.sh <review-text-file>}"
GITHUB_OUTPUT="${GITHUB_OUTPUT:-/dev/null}"

python3 - "$REVIEW_FILE" "$GITHUB_OUTPUT" << 'EOF'
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
        text = f.read()
except Exception:
    record("false", "missing-file")

if not text.strip():
    record("false", "no-output")

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
            m = re.match(r'[ ]{0,3}(`{3,}|~{3,})[ \t]*$', line)
            if m and m.group(1)[0] == fence_char and len(m.group(1)) >= fence_len:
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
        m = re.match(r'[ ]{0,3}(`{3,}|~{3,})', line)
        if m:
            fence_char = m.group(1)[0]
            fence_len = len(m.group(1))
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

lines = strip_machine_payloads(text.strip().splitlines())
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

content_lines = []
for line in verdict_lines:
    if re.search(r'^[ \t>*_#-]*verdict[: \t*_-]*$', line, re.IGNORECASE) or \
       re.search(r'^[ \t]*#{1,6}[ \t]+(\*\*)?verdict[: \t*_-]*$', line, re.IGNORECASE):
        continue
    if line.strip():
        content_lines.append(line.strip())

if not content_lines:
    content_lines = [l.strip() for l in verdict_lines if l.strip()]

if not content_lines:
    record("false", "no-verdict")

def strip_emphasis(s):
    # Strip markdown bold, italic, strikethrough, code ticks so inline styling around words is normalized
    return re.sub(r'[*_~`]+', ' ', s)

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
positive_targets = r'(ready\s+(?:for|to)\s+merge|ready(?!\s+(?:for|to)\b)|approved|clean|lgtm)'
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
footer_regex = re.compile(
    r'^[ \t>*_#-]*(\*\*)?(stopping\s+point|reviewed\s+commit|posted\s+by)\b',
    re.IGNORECASE
)

# Single ordered scan in document order: last verdict statement wins
last_verdict = None

for line in content_lines:
    if footer_regex.search(line):
        continue

    norm_line = expand_contractions(strip_emphasis(line))
    neg_pos_spans = []
    neg_neg_spans = []
    line_matches = []

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

