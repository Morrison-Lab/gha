#!/usr/bin/env bash
# List a PR's changed paths, or fail closed if the list cannot be trusted.
#
# GET /repos/{owner}/{repo}/pulls/{pull_number}/files is capped at 3000
# files (GitHub REST "List pull requests files", read 2026-08-26).
# `gh api --paginate` follows pages until GitHub stops, and a 200 with
# 3000 files is success --- so comparing against the PR's changed_files
# count is what detects a truncated tree. A large PR could otherwise hide
# a workflow edit and dispatch `--ref` at untrusted YAML (gha#598).
#
# Used by detect-pr-workflow-edits/action.yml and dispatch-review.sh.
# Callers that cannot invoke this script (dispatch-on-comment jobs with
# no checkout; @v2-pinned install-gha-scripts until the tag slides) copy
# the listed < changed_files comparison; keep those copies in sync.
#
# Usage: list-pr-changed-files.sh
# Env:
#   REPO                owner/name (required)
#   PR_NUMBER           pull request number (required)
#   GITHUB_PR_FILES_CAP endpoint file limit (optional, default 3000)
# Prints filenames to stdout, one per line.
# Exit:
#   0  complete list (may be empty)
#   1  usage
#   2  API failure or truncated list
set -euo pipefail

# Cap for GitHub's REST /pulls/{n}/files endpoint (GitHub caps at 3000 files).
# A listing that reaches or exceeds the cap is treated as truncated regardless
# of what .changed_files reports, protecting against .changed_files also being
# capped or clamped (gha#917).
GITHUB_PR_FILES_CAP="${GITHUB_PR_FILES_CAP:-3000}"

if [ -z "${REPO:-}" ] || [ -z "${PR_NUMBER:-}" ]; then
  echo "list-pr-changed-files.sh: REPO and PR_NUMBER are required" >&2
  exit 1
fi

if ! pr_json=$(gh api "repos/$REPO/pulls/$PR_NUMBER"); then
  echo "list-pr-changed-files.sh: could not read PR #$PR_NUMBER" >&2
  exit 2
fi

changed=$(printf '%s' "$pr_json" | jq -r '.changed_files')
if [ -z "$changed" ] || [ "$changed" = "null" ] || ! [[ "$changed" =~ ^[0-9]+$ ]]; then
  echo "list-pr-changed-files.sh: PR #$PR_NUMBER has no usable changed_files count" >&2
  exit 2
fi

if ! files=$(gh api "repos/$REPO/pulls/$PR_NUMBER/files?per_page=100" --paginate --jq '.[].filename'); then
  echo "list-pr-changed-files.sh: could not list files for PR #$PR_NUMBER" >&2
  exit 2
fi

listed=0
if [ -n "$files" ]; then
  listed=$(printf '%s\n' "$files" | grep -c . || true)
fi

if [ "$listed" -ge "$GITHUB_PR_FILES_CAP" ] || [ "$listed" -lt "$changed" ]; then
  if [ "$listed" -ge "$GITHUB_PR_FILES_CAP" ]; then
    echo "list-pr-changed-files.sh: listed $listed files for PR #$PR_NUMBER, reaching the $GITHUB_PR_FILES_CAP-file endpoint cap (changed_files=$changed); failing closed because the list may be truncated" >&2
  else
    echo "list-pr-changed-files.sh: listed $listed of $changed files for PR #$PR_NUMBER (GitHub caps this endpoint at $GITHUB_PR_FILES_CAP)" >&2
  fi
  exit 2
fi

if [ -n "$files" ]; then
  printf '%s\n' "$files"
fi
