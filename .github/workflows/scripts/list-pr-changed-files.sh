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
#   REPO        owner/name (required)
#   PR_NUMBER   pull request number (required)
# Prints filenames to stdout, one per line.
# Exit:
#   0  complete list (may be empty)
#   1  usage
#   2  API failure or truncated list
set -euo pipefail

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

if [ "$listed" -lt "$changed" ]; then
  echo "list-pr-changed-files.sh: listed $listed of $changed files for PR #$PR_NUMBER (GitHub caps this endpoint at 3000)" >&2
  exit 2
fi

if [ -n "$files" ]; then
  printf '%s\n' "$files"
fi
