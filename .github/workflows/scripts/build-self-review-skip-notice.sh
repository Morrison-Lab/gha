#!/usr/bin/env bash
# Generates the markdown notice comment body posted when self-review is skipped
# because a PR edits a workflow file. Extracted from claude-code-review.yml so
# the notice assembly and its run-URL matching contract can be unit-tested
# offline (gha#441).
#
# Usage: build-self-review-skip-notice.sh <workflow-path> <run-url> [caller-wf-path]
# Prints the formatted markdown notice to stdout.
set -euo pipefail

WF_PATH="${1:?usage: build-self-review-skip-notice.sh <workflow-path> <run-url> [caller-wf-path]}"
RUN_URL="${2:?usage: build-self-review-skip-notice.sh <workflow-path> <run-url> [caller-wf-path]}"
CALLER_WF="${3:-$WF_PATH}"

printf '> [!WARNING]\n'
if [ "$WF_PATH" = "$CALLER_WF" ]; then
  printf '> **No review ran --- this PR edits `%s`, the review workflow itself.**\n' "$WF_PATH"
  printf '> `claude-code-action` requires that file to match the default branch, so its token exchange fails until this change merges.\n'
else
  printf '> **No review ran --- this PR edits `%s`.**\n' "$WF_PATH"
  printf '> `claude-code-action` requires workflow files to match the default branch on dispatched runs, so its token exchange fails until this change merges.\n'
fi
printf '> The review is skipped by design, and re-running or re-dispatching will not change that: the skip lifts only if the PR stops editing that file.\n'
printf '>\n'
printf '> `require-review` reports a gray *skipped* rather than green.\n'
printf '> A green there attests that a reviewer ran, never that one approved; here none ran at all.\n'
printf '> Merge on a self-review or a human review instead.\n'
printf '>\n'
printf '> [View run](%s)\n' "$RUN_URL"
