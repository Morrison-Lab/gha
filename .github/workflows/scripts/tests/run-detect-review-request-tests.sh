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
  # An object pointing back at the PR is fine, and so is prose on later lines.
  "true|@claude review this"
  "true|@claude review again"
  "true|@claude please review the latest changes"
  $'true|@claude review\n\nI pushed a fix for the flaky test.'
  $'true|@claude, please review\n\nthanks!'
  # ... but an object naming something to go look at is a request to the
  # agent, not a dispatch keyword. Accepting these was the cost of admitting
  # the polite lead-ins above: they route a question to the read-only reviewer
  # and suppress the agent's own reply to it (gha#346).
  "false|@claude can you review this and also fix the failing test?"
  "false|@claude please review my reasoning in the issue description above"
  "false|@claude, can you review why the coverage job is flaky and patch it?"
  "false|@claude could you review the docs and update them if wrong"
  # Known false negatives, pinned so the contract is explicit rather than
  # discovered. Both are pure review requests carrying no instruction to the
  # agent, and both dispatched before the tail was constrained. Widening
  # TAIL_WORD would recover them; these cases make that a deliberate decision
  # instead of a drift (gha#346).
  "false|@claude review the changes I just pushed"
  "false|@claude please review when you get a chance"
  # CRLF is what GitHub actually delivers, and the pattern anchors on a bare
  # newline, so the normalizer has to strip the CRs for any of the above to
  # hold in production (gha#346).
  $'true|@claude review\r\nI pushed a fix.'
  $'false|> @claude review\r\n> yes\r'
  # Quote-replies cite somebody else's request; they are not a fresh one.
  "false|> @claude review"
  $'false|> @claude review\n>\n> ...as I said above'
  $'true|> @claude review\n\n@claude review'
  # Code spans and fences are the same idea as a blockquote, one and two
  # constructs down: standard Markdown for "this is a literal string, not
  # something I mean". Documenting the accepted phrasings used to dispatch a
  # review, so writing this very table down cost a run (gha#344).
  'false|the accepted phrasings are `@claude review` and `@claude, review`'
  # The span has to end the line, or the trailing prose alone makes this
  # false and the case proves nothing about run-length matching.
  'false|the double-backtick form is ``@claude review``'
  $'false|An example caller comment:\n\n```\n@claude review\n```'
  $'false|~~~\n@claude, please review\n~~~'
  # ... but a genuine request in the prose still dispatches, even when the
  # same comment also quotes the phrasing. Stripping must not become a way to
  # suppress a real request that happens to sit near an example.
  $'true|@claude review\n\nFor reference the other accepted form is `@claude, review`.'
  $'true|Here is the failing config:\n\n```yaml\nreview: true\n```\n\n@claude please review'
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
  # Gemini and AI review trigger variants
  'true|@ai review'
  'true|@ai-review'
  'true|@gemini review'
  'true|@gemini-cli review'
)

failures=0
for case in "${cases[@]}"; do
  want="${case%%|*}"
  body="${case#*|}"
  got="$(printf '%s\0' "$body" | bash "$detect_script")"
  if [[ "$got" == "$want" ]]; then
    echo "OK   detect-review-request.sh ${body@Q} -> $got"
  else
    echo "::error::detect-review-request.sh ${body@Q}: expected $want but got $got"
    failures=$((failures + 1))
  fi
done

# Multiple bodies: claude.yml passes the comment and review bodies together,
# and its late-comment scan appends every comment posted after the trigger,
# so `any of` matters.
if [[ "$(printf '%s\0' "not a request" "@claude please review" | bash "$detect_script")" != "true" ]]; then
  echo "::error::detect-review-request.sh did not match a review request in a later body"
  failures=$((failures + 1))
else
  echo "OK   detect-review-request.sh matches a request in any body"
fi

# A body larger than Linux's per-argument MAX_ARG_STRLEN (131072 bytes). The
# first implementation passed bodies as positional arguments, so a single
# emoji-heavy comment -- well inside GitHub's 65536-character cap, but up to
# 256 KiB in 4-byte UTF-8 -- failed `execve` with E2BIG and reddened the whole
# claude job (gha#341 review). Reverting the stdin rewrite makes this case
# fail; nothing else in the table reaches the limit.
huge="$(head -c 200000 /dev/zero | tr '\0' 'x')"
if [[ "$(printf '%s\0' "$huge" "@claude please review" | bash "$detect_script")" != "true" ]]; then
  echo "::error::detect-review-request.sh failed on a body larger than MAX_ARG_STRLEN"
  failures=$((failures + 1))
else
  echo "OK   detect-review-request.sh handles a body larger than MAX_ARG_STRLEN"
fi

# No bodies at all can only mean a miswired caller, so fail loudly rather
# than reporting a confident "false".
if bash "$detect_script" </dev/null >/dev/null 2>&1; then
  echo "::error::detect-review-request.sh should exit non-zero on empty stdin"
  failures=$((failures + 1))
else
  echo "OK   detect-review-request.sh rejects empty stdin"
fi

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures of $(( ${#cases[@]} + 3 )) detect-review-request case(s) did not behave as expected"
  exit 1
fi
echo "All $(( ${#cases[@]} + 3 )) detect-review-request cases behaved as expected."
