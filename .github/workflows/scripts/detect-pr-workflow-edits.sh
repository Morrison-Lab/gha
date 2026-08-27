#!/usr/bin/env bash
# Classify whether a PR's changed-file list includes top-level GitHub
# Actions workflow YAML, and whether that set includes the caller review
# workflow.
#
# Top-level means `.github/workflows/<file>.yml` / `.yaml` only --- not
# `.github/workflows/scripts/...` and not composite actions under
# `.github/actions/`. That is the same path class GitHub executes as
# workflows, and the same grep claude-code-review.yml used before gha#598
# to skip dispatched reviews (gha#386).
#
# Used by:
#   - claude-code-review.yml, to restore default-branch copies instead of
#     skipping the review
#   - dispatch-review.sh, to omit `--ref` so GitHub executes the
#     default-branch caller rather than the PR head's YAML
#
# Usage: detect-pr-workflow-edits.sh
# Env:
#   PR_CHANGED_FILES  newline-separated paths (required; may be empty)
#   CALLER_WF_PATH    e.g. .github/workflows/claude-review.yml (optional)
# Prints:
#   workflow_edits=true|false
#   caller_edited=true|false
#   edited_path=<first matching workflow, or empty>
set -euo pipefail

# A missing variable is a caller bug: treating it as "no files" would
# report a clean tree and dispatch `--ref` at an untrusted head.
if [ -z "${PR_CHANGED_FILES+x}" ]; then
  echo "detect-pr-workflow-edits.sh: PR_CHANGED_FILES is unset" >&2
  exit 2
fi

CALLER_WF_PATH="${CALLER_WF_PATH:-}"

# Strip CR so a CRLF list from the GitHub API still matches.
files=$(printf '%s' "$PR_CHANGED_FILES" | tr -d '\r')

workflow_edits=false
caller_edited=false
edited_path=""

while IFS= read -r path || [ -n "$path" ]; do
  [ -z "$path" ] && continue
  case "$path" in
    .github/workflows/*.yml|.github/workflows/*.yaml)
      # Reject nested paths: .github/workflows/scripts/foo.yml has extra
      # slashes after workflows/.
      rest="${path#.github/workflows/}"
      case "$rest" in
        */*) continue ;;
      esac
      workflow_edits=true
      if [ -z "$edited_path" ]; then
        edited_path="$path"
      fi
      if [ -n "$CALLER_WF_PATH" ] && [ "$path" = "$CALLER_WF_PATH" ]; then
        caller_edited=true
      fi
      ;;
  esac
done <<< "$files"

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "workflow_edits=$workflow_edits" >> "$GITHUB_OUTPUT"
  echo "caller_edited=$caller_edited" >> "$GITHUB_OUTPUT"
  echo "edited_path=$edited_path" >> "$GITHUB_OUTPUT"
fi

echo "workflow_edits=$workflow_edits"
echo "caller_edited=$caller_edited"
echo "edited_path=$edited_path"
