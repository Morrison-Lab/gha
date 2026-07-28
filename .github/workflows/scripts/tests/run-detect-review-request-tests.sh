#!/usr/bin/env bash
# Exercises detect-review-request.sh offline, mirroring
# run-sum-costs-tests.sh's pattern. Wired into _selftest.yml's
# `review-fail-check` job (gha#339).
#
# The cases below are the contract, not a sample: claude.yml suppresses the
# agent's own prose reply whenever this script returns true, so both a missed
# request and a misfire are user-visible, and neither shows up until a real
# comment hits the workflow.
#
# Usage: bash .github/workflows/scripts/tests/run-detect-review-request-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
detect_script="$repo_root/.github/workflows/scripts/detect-review-request.sh"

# "<expected>|<body>" -- `|` never appears in a body below.
cases=(
  # Requests the previous `@claude[[:space:]]+review` pattern already caught.
  "true|@claude review"
  "true|@claude  review"
  $'true|Thanks for the fix.\n\n@claude review'
  # Punctuated and polite phrasings it missed (serodynamics#276, #277).
  "true|@claude, please review"
  "true|@claude, review"
  "true|@claude please review this PR"
  "true|@claude can you review this?"
  "true|@claude could you please review"
  "true|@claude would you review the latest push"
  "true|@claude kindly review"
  "true|@claude pls review"
  "true|@claude plz review"
  "true|@claude re-review please"
  "true|@CLAUDE Review"
  # Quote-replies cite somebody else's request; they are not a fresh one.
  "false|> @claude review"
  $'false|> @claude review\n>\n> ...as I said above'
  $'true|> @claude review\n\n@claude review'
  # An @claude request that merely contains the word "review". Matching these
  # would swallow the agent's reply to the question actually being asked.
  "false|@claude the review workflow is broken, can you fix it?"
  "false|@claude I have addressed your review comments"
  "false|@claude take another look at the review job"
  # `review` must be a whole word.
  "false|@claude reviewer assignments are wrong"
  # No mention at all, and a mention with no request.
  "false|Please review this."
  "false|@claude what does this function do?"
  "false|"
)

failures=0
for case in "${cases[@]}"; do
  want="${case%%|*}"
  body="${case#*|}"
  got="$(bash "$detect_script" "$body")"
  if [[ "$got" == "$want" ]]; then
    echo "OK   detect-review-request.sh ${body@Q} -> $got"
  else
    echo "::error::detect-review-request.sh ${body@Q}: expected $want but got $got"
    failures=$((failures + 1))
  fi
done

# Multiple bodies: claude.yml passes the comment and review bodies together,
# and its late-comment scan feeds them in one at a time, so `any of` matters.
if [[ "$(bash "$detect_script" "not a request" "@claude please review")" != "true" ]]; then
  echo "::error::detect-review-request.sh did not match a review request in a later argument"
  failures=$((failures + 1))
else
  echo "OK   detect-review-request.sh matches a request in any argument"
fi

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures of $(( ${#cases[@]} + 1 )) detect-review-request case(s) did not behave as expected"
  exit 1
fi
echo "All $(( ${#cases[@]} + 1 )) detect-review-request cases behaved as expected."
