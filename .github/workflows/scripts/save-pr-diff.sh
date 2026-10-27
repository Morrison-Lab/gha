#!/usr/bin/env bash
# Saves the PR diff to a target file for the reviewer, removing partial files
# on failure and setting GITHUB_OUTPUT `path` to the absolute target path
# (or empty on failure).
#
# Inputs via env / args:
#   PR_NUMBER (or arg 1)
#   REPO (or GITHUB_REPOSITORY)
#   TARGET_PATH (or DIFF_NAME relative to GITHUB_WORKSPACE)
#
# Contract:
#   Emits path=<absolute-path> on GITHUB_OUTPUT on success
#   Emits path= on GITHUB_OUTPUT on failure/empty
#   Exits 0 always (warns on failure rather than failing the job)
set -uo pipefail

PR_NUMBER="${1:-${PR_NUMBER:-}}"
REPO="${2:-${REPO:-${GITHUB_REPOSITORY:-}}}"
TARGET="${3:-${TARGET_PATH:-${GITHUB_WORKSPACE:-.}/${DIFF_NAME:-.claude-review-pr.diff}}}"

if [ -z "$PR_NUMBER" ] || [ -z "$REPO" ]; then
  echo "::warning::save-pr-diff: PR_NUMBER and REPO are required."
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "path=" >> "$GITHUB_OUTPUT"
  fi
  exit 0
fi

mkdir -p "$(dirname "$TARGET")"

# `gh pr diff` fails for a PR that changes more than 300 files (HTTP 406), so
# fall back to the per-file patches from the files API, which reaches 3000 files.
#
# The saved diff is approximate: the headers are synthesized (no `index` line,
# `a/` for added files), and a file the API returns no patch for, such as a
# binary or oversized one, carries a marker line instead of a body. The API
# caps at 3000 files, so a PR past that cap saves a partial diff; the plain
# log line below makes the fallback visible in the log. It is not a `::notice::`
# annotation, because annotation-gate fails a head that carries one.
files_api_diff() {
  echo "gh pr diff failed or was empty; saving an approximate diff from the files API." >&2
  gh api --paginate "repos/$REPO/pulls/$PR_NUMBER/files" --jq '.[] |
    "diff --git a/\(.previous_filename // .filename) b/\(.filename)\n--- a/\(.previous_filename // .filename)\n+++ b/\(.filename)\n\(.patch // "[patch omitted by the files API]")"'
}

if { gh pr diff "$PR_NUMBER" --repo "$REPO" > "$TARGET" && [ -s "$TARGET" ]; } \
  || { files_api_diff > "$TARGET" && [ -s "$TARGET" ]; }; then
  # Resolve to absolute path
  ABS_TARGET="$(cd "$(dirname "$TARGET")" && pwd)/$(basename "$TARGET")"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "path=$ABS_TARGET" >> "$GITHUB_OUTPUT"
  fi
  echo "Saved the PR diff for the reviewer: $ABS_TARGET ($(wc -c < "$TARGET") bytes)."
else
  rm -f "$TARGET"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "path=" >> "$GITHUB_OUTPUT"
  fi
  echo "::warning::Could not save the PR diff to $TARGET (gh pr diff and the files API both failed); the reviewer will fall back to calling gh pr diff itself."
fi
