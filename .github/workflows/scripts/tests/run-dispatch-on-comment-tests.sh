#!/usr/bin/env bash
# Asserts matching behavior for the /review command in claude-review.yml's
# dispatch-on-comment job (gha#908).
#
# Usage: bash .github/workflows/scripts/tests/run-dispatch-on-comment-tests.sh
set -euo pipefail

matches_review_comment() {
  local comment_body="$1"
  shopt -s nocasematch
  if [[ "$comment_body" =~ ^/review([[:space:]]|$) ]]; then
    shopt -u nocasematch
    return 0
  fi
  shopt -u nocasematch
  return 1
}

# format: expected (true/false) | input string
cases=(
  # Standard lowercase forms
  "true|/review"
  "true|/review "
  "true|/review please"
  "true|/review	with tab"
  $'true|/review\nwith newline'

  # Mixed/uppercase spellings (gha#908)
  "true|/Review"
  "true|/REVIEW"
  "true|/ReViEw"
  "true|/Review please"
  $'true|/Review\nwith newline'
  "true|/REVIEW "

  # Non-matching forms (must stay false)
  "false|/reviewer"
  "false|/Reviewer"
  "false|/REVIEWER"
  "false|/reviewing"
  "false|not a review /review"
  "false|hello /review"
  "false|review"
  "false|/rev"
  "false|"
)

failed=0
for entry in "${cases[@]}"; do
  expected="${entry%%|*}"
  body="${entry#*|}"

  if matches_review_comment "$body"; then
    actual="true"
  else
    actual="false"
  fi

  if [[ "$actual" != "$expected" ]]; then
    echo "FAIL: expected $expected, got $actual for input: $(printf '%q' "$body")" >&2
    failed=$((failed + 1))
  fi
done

if [[ $failed -gt 0 ]]; then
  echo "::error::$failed dispatch-on-comment test(s) failed." >&2
  exit 1
fi

echo "OK: All ${#cases[@]} dispatch-on-comment tests passed."
