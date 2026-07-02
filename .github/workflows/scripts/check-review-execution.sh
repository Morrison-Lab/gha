#!/usr/bin/env bash
# Shared logic for claude-code-review.yml's "Fail the check if the review did
# not complete" step, extracted to a standalone script so it can be exercised
# offline against canned execution-output fixtures (see
# .github/workflows/scripts/tests/), without a live Claude API call (#174).
#
# Usage: check-review-execution.sh <execution-file>
#
# Reads a claude-code-action execution-output file (NDJSON stream or a single
# JSON array of stream-json messages), and:
#   - fails if the file is missing, has no `result` object, or the result is
#     an error that isn't a quota/auth pre-processing rejection;
#   - writes quota_exhausted=true to $GITHUB_OUTPUT (if set) and exits 0 on a
#     zero-cost, single-turn error result (quota exhaustion / auth failure);
#   - fails if the run's final assistant text is empty/whitespace-only, or is
#     missing the `### Verdict` heading every finished review must contain
#     (Lacaedemon/sparta#590 — catches stub/placeholder reviews);
#   - otherwise writes review_text_file=<path> to $GITHUB_OUTPUT and exits 0.
#
# $GITHUB_OUTPUT is optional so this can run standalone in a test harness;
# when unset, output assignments are silently dropped.
set -euo pipefail

EXECUTION_FILE="${1:?usage: check-review-execution.sh <execution-file>}"
GITHUB_OUTPUT="${GITHUB_OUTPUT:-/dev/null}"

if [[ ! -f "$EXECUTION_FILE" ]]; then
  echo "::error::Claude review produced no execution output — treating as a failed review."
  exit 1
fi
# Handles NDJSON stream or a single JSON array; grabs the last result object.
result="$(jq -s 'flatten | map(select(.type=="result")) | last // empty' "$EXECUTION_FILE")"
if [[ -z "$result" || "$result" == "null" ]]; then
  echo "::error::No result object in execution output — review did not finish."
  exit 1
fi
is_error="$(jq -r '.is_error // false' <<< "$result")"
subtype="$(jq -r '.subtype // ""' <<< "$result")"
if [[ "$is_error" == "true" || "$subtype" == error_* ]]; then
  # total_cost_usd==0 with num_turns==1 means the API rejected the
  # request before any real processing — quota exhaustion, auth
  # failure, or an immediate network error. Skip gracefully.
  total_cost="$(jq -r '.total_cost_usd // 1' <<< "$result")"
  num_turns="$(jq -r '.num_turns // 0' <<< "$result")"
  if [[ "$total_cost" == "0" && "$num_turns" == "1" ]]; then
    echo "quota_exhausted=true" >> "$GITHUB_OUTPUT"
    echo "::warning::Claude review skipped — CLAUDE_CODE_OAUTH_TOKEN quota or auth error (zero cost, turn 1). Re-trigger the review once the quota resets."
    exit 0
  fi
  echo "::error::Claude review ended in an error state (is_error=$is_error, subtype=$subtype)."
  jq '{subtype, is_error, num_turns, duration_ms, total_cost_usd, permission_denials_count}' <<< "$result" || true
  exit 1
fi
# Guard against a run that reports is_error:false but never
# actually produced a review — e.g. it exits after posting only an
# orchestration placeholder ("waiting for background agents...",
# "Still waiting on the remaining three review agents...") instead
# of finished findings. subtype/is_error can't catch this because
# the SDK call itself succeeded; only the content reveals the
# review never finished (Lacaedemon/sparta#590). Enumerating every
# phrasing of "I'm still waiting" is a losing game (gha#172 review),
# so check instead for the one thing every *finished* review is
# required to contain: the "### Verdict" heading mandated by this
# prompt above. A stub is narration, never a finished review, so it
# can't have produced that heading.
review_text_file="$(mktemp)"
jq -rs 'flatten | [.[] | select(.type == "assistant") | .message.content[]? | select(.type == "text") | .text] | last // ""' "$EXECUTION_FILE" > "$review_text_file" 2>/dev/null || true
if [[ -z "$(tr -d '[:space:]' < "$review_text_file")" ]]; then
  echo "::error::Claude review produced no review text — treating as a failed review."
  exit 1
fi
if ! grep -qiE '^###[[:space:]]*verdict\b' "$review_text_file"; then
  echo "::error::Claude review has no '### Verdict' heading — looks like an incomplete/stub review, not a finished one (Lacaedemon/sparta#590)."
  exit 1
fi
echo "review_text_file=$review_text_file" >> "$GITHUB_OUTPUT"
echo "Claude review completed cleanly (subtype=$subtype)."
