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

if [[ ! -f "$REVIEW_FILE" ]]; then
  echo "clean=false" >> "$GITHUB_OUTPUT"
  echo "verdict=missing-file" >> "$GITHUB_OUTPUT"
  echo "clean=false"
  echo "verdict=missing-file"
  exit 0
fi

if [[ -z "$(tr -d '[:space:]' < "$REVIEW_FILE")" ]]; then
  echo "clean=false" >> "$GITHUB_OUTPUT"
  echo "verdict=no-output" >> "$GITHUB_OUTPUT"
  echo "clean=false"
  echo "verdict=no-output"
  exit 0
fi

# Extract the verdict section: from the first verdict header/label to EOF.
verdict_section_file="$(mktemp)"
awk 'BEGIN{found=0} tolower($0) ~ /^[[:space:]>*_#-]*verdict/ {found=1} found'   "$REVIEW_FILE" > "$verdict_section_file"

if [[ -z "$(tr -d '[:space:]' < "$verdict_section_file")" ]]; then
  echo "clean=false" >> "$GITHUB_OUTPUT"
  echo "verdict=no-verdict" >> "$GITHUB_OUTPUT"
  echo "clean=false"
  echo "verdict=no-verdict"
  exit 0
fi

# Look for the primary verdict line immediately under/following the Verdict header.
# In Claude reviews following the standard format:
#   ### Verdict
#   **Ready for merge** — ...
# or
#   **Verdict:** Ready for merge
# or
#   Verdict: Needs more work
#
# We strip the leading `### Verdict` header line itself to inspect the verdict declaration.
declaration="$(grep -viE '^[[:space:]>*_#-]*verdict[:[:space:]]*$' "$verdict_section_file" | grep -vE '^[[:space:]]*$' | head -n 1 || true)"

# Fall back to the whole verdict section if declaration extraction is empty.
if [[ -z "$declaration" ]]; then
  declaration="$(cat "$verdict_section_file")"
fi

# Classify based on declaration and verdict section.
# First check if the declaration starts with or clearly states a non-clean verdict:
if echo "$declaration" | grep -qiE '\b(needs\s+more\s+work|changes\s+requested|changes\s+required|not\s+ready|actionable\s+findings|blocked|impasse|deadlock|rejected|unapproved)\b'; then
  # Verify it's not a negated mention like "no changes requested" or "zero actionable findings"
  if ! echo "$declaration" | grep -qiE '\b(no|zero|0|without)\s+(needs\s+more\s+work|changes\s+requested|changes\s+required|actionable\s+findings|blocking\s+findings|blockers?)\b'; then
    slug="needs-more-work"
    if echo "$declaration" | grep -qiE '\bchanges\s+requested\b'; then
      slug="changes-requested"
    elif echo "$declaration" | grep -qiE '\bblocked\b'; then
      slug="blocked"
    elif echo "$declaration" | grep -qiE '\bimpasse|deadlock\b'; then
      slug="impasse"
    elif echo "$declaration" | grep -qiE '\brejected|unapproved\b'; then
      slug="rejected"
    fi
    echo "clean=false" >> "$GITHUB_OUTPUT"
    echo "verdict=$slug" >> "$GITHUB_OUTPUT"
    echo "clean=false"
    echo "verdict=$slug"
    exit 0
  fi
fi

# Check for affirmative clean status:
if echo "$declaration" | grep -qiE '\b(ready\s+for\s+merge|clean|approved|passed|lgtm|no\s+findings|no\s+blocking\s+issues|no\s+blocking\s+findings|no\s+actionable\s+findings)\b'; then
  slug="ready-for-merge"
  if echo "$declaration" | grep -qiE '\bapproved\b'; then
    slug="approved"
  elif echo "$declaration" | grep -qiE '\bclean\b'; then
    slug="clean"
  fi
  echo "clean=true" >> "$GITHUB_OUTPUT"
  echo "verdict=$slug" >> "$GITHUB_OUTPUT"
  echo "clean=true"
  echo "verdict=$slug"
  exit 0
fi

# If neither clear pattern matched the declaration line, scan the full verdict section:
if grep -qiE '\b(needs\s+more\s+work|changes\s+requested|changes\s+required)\b' "$verdict_section_file" &&    ! grep -qiE '\b(no|zero|0|without)\s+(needs\s+more\s+work|changes\s+requested|changes\s+required)\b' "$verdict_section_file"; then
  echo "clean=false" >> "$GITHUB_OUTPUT"
  echo "verdict=needs-more-work" >> "$GITHUB_OUTPUT"
  echo "clean=false"
  echo "verdict=needs-more-work"
  exit 0
fi

if grep -qiE '\b(ready\s+for\s+merge|clean|approved)\b' "$verdict_section_file"; then
  echo "clean=true" >> "$GITHUB_OUTPUT"
  echo "verdict=ready-for-merge" >> "$GITHUB_OUTPUT"
  echo "clean=true"
  echo "verdict=ready-for-merge"
  exit 0
fi

# Unrecognized verdict format: fail-closed (clean=false).
echo "clean=false" >> "$GITHUB_OUTPUT"
echo "verdict=unrecognized" >> "$GITHUB_OUTPUT"
echo "clean=false"
echo "verdict=unrecognized"
exit 0
