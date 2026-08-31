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

bold_status_regex = re.compile(r'\*\*([^*]+)\*\*')

non_clean_kw = re.compile(
    r'\b(needs\s+more\s+work|changes\s+requested|changes\s+required|not\s+ready|blocked|impasse|deadlock|rejected|unapproved)\b',
    re.IGNORECASE
)
clean_kw = re.compile(
    r'\b(ready\s+for\s+merge|clean|approved|passed|lgtm|no\s+findings|no\s+blocking\s+issues|no\s+blocking\s+findings|no\s+actionable\s+findings)\b',
    re.IGNORECASE
)
negated_clean_phrases = re.compile(
    r'\b(no|zero|0|without)\s+(needs\s+more\s+work|changes\s+requested|changes\s+required|actionable\s+findings|blocking\s+findings|blocking\s+issues|blockers?)\b',
    re.IGNORECASE
)

# 1. Check for bold status tokens (last one wins)
last_bold_verdict = None
for line in content_lines:
    for m in bold_status_regex.finditer(line):
        bold_text = m.group(1).strip()
        defanged = negated_clean_phrases.sub('_CLEAN_PHRASE_', bold_text)
        if non_clean_kw.search(defanged):
            slug = 'needs-more-work'
            if re.search(r'\bchanges\s+requested\b', defanged, re.I): slug = 'changes-requested'
            elif re.search(r'\bblocked\b', defanged, re.I): slug = 'blocked'
            elif re.search(r'\bimpasse|deadlock\b', defanged, re.I): slug = 'impasse'
            elif re.search(r'\brejected|unapproved\b', defanged, re.I): slug = 'rejected'
            last_bold_verdict = ("false", slug)
        elif clean_kw.search(bold_text) or '_CLEAN_PHRASE_' in defanged:
            slug = 'ready-for-merge'
            if re.search(r'\bapproved\b', bold_text, re.I): slug = 'approved'
            elif re.search(r'\bclean\b', bold_text, re.I): slug = 'clean'
            last_bold_verdict = ("true", slug)

if last_bold_verdict is not None:
    record(*last_bold_verdict)

# 2. Check full lines in verdict section
# First check for unnegated non-clean assertions
for line in content_lines:
    defanged = negated_clean_phrases.sub('_CLEAN_PHRASE_', line)
    if non_clean_kw.search(defanged):
        slug = 'needs-more-work'
        if re.search(r'\bchanges\s+requested\b', defanged, re.I): slug = 'changes-requested'
        elif re.search(r'\bblocked\b', defanged, re.I): slug = 'blocked'
        elif re.search(r'\bimpasse|deadlock\b', defanged, re.I): slug = 'impasse'
        elif re.search(r'\brejected|unapproved\b', defanged, re.I): slug = 'rejected'
        record("false", slug)

# Then check for clean assertions
for line in content_lines:
    defanged = negated_clean_phrases.sub('_CLEAN_PHRASE_', line)
    if clean_kw.search(line) or '_CLEAN_PHRASE_' in defanged:
        slug = 'ready-for-merge'
        if re.search(r'\bapproved\b', line, re.I): slug = 'approved'
        elif re.search(r'\bclean\b', line, re.I): slug = 'clean'
        record("true", slug)

record("false", "unrecognized")
EOF
