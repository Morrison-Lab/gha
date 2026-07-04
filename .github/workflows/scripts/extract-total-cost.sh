#!/usr/bin/env bash
# Extracts total_cost_usd from a claude-code-action execution-output file's
# last "result" event and writes cost=<value> to $GITHUB_OUTPUT (silently
# writes nothing if the file is missing or the field is absent). Shared by
# claude.yml's two comment-posting call sites -- the no-code-committed
# response and the issue-trigger finalize comment -- both of which read the
# SAME steps.claude.outputs.execution_file, so this runs once and both
# downstream steps read its output rather than duplicating the jq filter
# (gha#219 review finding 1).
#
# Usage: extract-total-cost.sh <execution-file>
#
# $GITHUB_OUTPUT is optional so this can run standalone in a test harness;
# when unset, the output assignment is silently dropped.
set -euo pipefail

EXECUTION_FILE="${1:?usage: extract-total-cost.sh <execution-file>}"
GITHUB_OUTPUT="${GITHUB_OUTPUT:-/dev/null}"

[[ -f "$EXECUTION_FILE" ]] || exit 0

COST="$(jq -rs 'flatten(1) | map(select(.type == "result")) | last.total_cost_usd // empty' "$EXECUTION_FILE")"
if [[ -n "$COST" ]]; then
  echo "cost=$COST" >> "$GITHUB_OUTPUT"
fi
