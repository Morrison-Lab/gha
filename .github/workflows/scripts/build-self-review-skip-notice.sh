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
# failure). The path still appears in the body so the collapse step and a
# reader can see which file was in play.
set -euo pipefail

WF_PATH="${1:?usage: build-self-review-skip-notice.sh <workflow-path> <run-url> [caller-wf-path]}"
RUN_URL="${2:?usage: build-self-review-skip-notice.sh <workflow-path> <run-url> [caller-wf-path]}"

printf '> [!WARNING]\n'
printf '> **No review ran --- restoring default-branch workflow files failed.**\n'
printf '> This PR edits `%s`. The review job tried to replace `.github/workflows/` with the default-branch copies so it would not execute untrusted workflow YAML from the PR head ([gha#598](https://github.com/Morrison-Lab/gha/issues/598)), and that restore failed.\n' "$WF_PATH"
printf '> The review is skipped rather than running against PR-head YAML. A later re-run can recover if fetching the default branch was the problem.\n'
printf '>\n'
printf '> `require-review` reports a gray *skipped* rather than green.\n'
printf '> A green there attests that a reviewer ran, never that one approved; here none ran at all.\n'
printf '>\n'
printf '> [View run](%s)\n' "$RUN_URL"
