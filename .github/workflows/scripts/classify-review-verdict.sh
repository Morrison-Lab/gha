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

lines = text.strip().splitlines()
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

