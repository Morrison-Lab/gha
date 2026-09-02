#!/usr/bin/env bash
# Pack claude-code-review.yml's posting inputs into a directory the posting
# job can download as an artifact (gha#580).
#
# The model job cannot hold pull-requests: write / issues: write, so every
# value the posting job needs has to leave that job as files rather than as
# live step outputs in the same job. This script is the only writer of that
# directory: the posting job reads payload.json by key, and the two sidecar
# files (review.txt, denied_tools.txt) exist only when the corresponding
# input was non-empty, so an absent file means "not recorded" rather than
# "empty string".
#
# Inputs arrive through the environment, never argv, because denied_tools is
# agent-authored free text (gha#541) and a review body is multi-line. jq
# --arg is what makes those values JSON rather than concatenated into a
# hand-rolled object.
#
# Usage (from the pack-review-payload composite, or offline):
#   PAYLOAD_DIR=... PR_NUMBER=... ... bash pack-review-payload.sh
#
# Writes:
#   $PAYLOAD_DIR/payload.json
#   $PAYLOAD_DIR/review.txt          (omitted when REVIEW_TEXT_FILE is empty/missing)
#   $PAYLOAD_DIR/denied_tools.txt    (omitted when DENIED_TOOLS is empty)
set -euo pipefail

if [[ -z "${PAYLOAD_DIR:-}" ]]; then
  echo "::error::PAYLOAD_DIR is required." >&2
  exit 1
fi

mkdir -p "$PAYLOAD_DIR"

# A path that exists but is empty is still a review (a genuine zero-length
# verdict is not a thing we have seen, but treating empty as missing would
# make a posting job look like "no review text" when the file was produced).
# Missing, or a directory, is "not recorded".
review_present=false
if [[ -n "${REVIEW_TEXT_FILE:-}" && -f "$REVIEW_TEXT_FILE" ]]; then
  cp "$REVIEW_TEXT_FILE" "$PAYLOAD_DIR/review.txt"
  review_present=true
fi

if [[ -n "${DENIED_TOOLS:-}" ]]; then
  # The posting job reads this through env:, never through ${{ }} in a run
  # body, for the same reason resolve-final does: the value is agent-authored.
  printf '%s\n' "$DENIED_TOOLS" > "$PAYLOAD_DIR/denied_tools.txt"
fi

# Every field the posting job branches on is a key here, including the ones
# that are empty on a given path, so a missing key is a pack bug rather than
# a legitimate "this path did not set it". Sidecar files are the exception
# (see the header): their absence is the three-valued signal.
jq -n \
  --arg schema_version "1" \
  --arg pr_number "${PR_NUMBER:-}" \
  --arg repo "${REPO:-}" \
  --arg run_url "${RUN_URL:-}" \
  --arg run_id "${RUN_ID:-}" \
  --arg event_name "${EVENT_NAME:-}" \
  --arg caller_wf_path "${CALLER_WF_PATH:-}" \
  --arg wf_path "${WF_PATH:-}" \
  --arg self_mod "${SELF_MOD:-false}" \
  --arg skip_notice_posted "${SKIP_NOTICE_POSTED:-false}" \
  --arg quota_exhausted "${QUOTA_EXHAUSTED:-false}" \
  --arg quota_reason "${QUOTA_REASON:-}" \
  --arg quota_message "${QUOTA_MESSAGE:-}" \
  --arg cancelled "${CANCELLED:-false}" \
  --arg resolve_outcome "${RESOLVE_OUTCOME:-}" \
  --arg head_sha "${HEAD_SHA:-}" \
  --arg total_cost_usd "${TOTAL_COST_USD:-}" \
  --arg failure_kind "${FAILURE_KIND:-}" \
  --arg denials "${DENIALS:-}" \
  --arg max_denials "${MAX_DENIALS:-}" \
  --arg attempts "${ATTEMPTS:-}" \
  --arg track_progress "${TRACK_PROGRESS:-false}" \
  --arg report_cost "${REPORT_COST:-true}" \
  --argjson review_present "$review_present" \
  '{
    schema_version: $schema_version,
    pr_number: $pr_number,
    repo: $repo,
    run_url: $run_url,
    run_id: $run_id,
    event_name: $event_name,
    caller_wf_path: $caller_wf_path,
    wf_path: $wf_path,
    self_mod: $self_mod,
    skip_notice_posted: $skip_notice_posted,
    quota_exhausted: $quota_exhausted,
    quota_reason: $quota_reason,
    quota_message: $quota_message,
    cancelled: $cancelled,
    resolve_outcome: $resolve_outcome,
    head_sha: $head_sha,
    total_cost_usd: $total_cost_usd,
    failure_kind: $failure_kind,
    denials: $denials,
    max_denials: $max_denials,
    attempts: $attempts,
    track_progress: $track_progress,
    report_cost: $report_cost,
    review_present: $review_present
  }' > "$PAYLOAD_DIR/payload.json"

echo "Packed review payload into $PAYLOAD_DIR"
