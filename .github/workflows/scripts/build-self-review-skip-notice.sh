#!/usr/bin/env bash
# Generates the markdown notice comment body posted when a review is skipped
# because restoring default-branch workflow files failed (gha#598). Extracted
# from claude-code-review.yml so the notice assembly and its run-URL matching
# contract can be unit-tested offline (gha#441).
#
# Usage: build-self-review-skip-notice.sh <workflow-path> <run-url> [caller-wf-path]
# Prints the formatted markdown notice to stdout.
#
# The third argument is kept so existing callers do not break; the notice no
# longer branches on caller-vs-other (every remaining skip is a restore
# failure). A real edited path still appears in the body so the collapse
# step and a reader can see which file was in play.
#
# An empty workflow-path means the PR file list could not be completed
# (API failure or GitHub's 3000-file cap). detect-pr-workflow-edits then
# sets workflow_edits=true with an empty edited_path rather than stuffing
# a fake filename into the notice.
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: build-self-review-skip-notice.sh <workflow-path> <run-url> [caller-wf-path]" >&2
  exit 1
fi

WF_PATH="$1"
RUN_URL="$2"
RESTORE_CLAUSE='The review job tried to replace `.github/workflows/` with the default-branch copies so it would not execute untrusted workflow YAML from the PR head ([gha#598](https://github.com/Morrison-Lab/gha/issues/598)), and that restore failed.'

printf '> [!WARNING]\n'
printf '> **No review ran --- restoring default-branch workflow files failed.**\n'
if [ -z "$WF_PATH" ]; then
  printf '> The PR changed-file list was incomplete, so the review treated it as a workflow-file edit rather than executing an unknown or truncated PR tree. %s\n' "$RESTORE_CLAUSE"
else
  printf '> This PR edits `%s`. %s\n' "$WF_PATH" "$RESTORE_CLAUSE"
fi
printf '> The review is skipped rather than running against PR-head YAML. A later re-run can recover if fetching the default branch was the problem.\n'
printf '>\n'
printf '> `require-review` reports a gray *skipped* rather than green.\n'
printf '> A green there attests that a reviewer ran, never that one approved; here none ran at all.\n'
printf '>\n'
printf '> [View run](%s)\n' "$RUN_URL"
