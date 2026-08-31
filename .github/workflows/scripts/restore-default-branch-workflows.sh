#!/usr/bin/env bash
# Replace `.github/workflows/` in the current checkout with the copy from
# a trusted ref (the repository's default branch), so a review job never
# leaves untrusted workflow YAML from the PR head on disk. (gha#598)
#
# `git checkout <ref> -- .github/workflows` updates files that exist on
# that ref; it does not delete a workflow the PR added. Removing the
# directory first, then restoring it, is what makes a PR-only file go
# away --- confirmed by the suite's extra-file case rather than assumed.
#
# Env:
#   DEFAULT_BRANCH  required (e.g. main)
#   DEFAULT_REF     optional override of the git ref to restore from
#                   (tests pass a local branch name; production leaves
#                   this empty so the script fetches origin/$DEFAULT_BRANCH)
set -euo pipefail

DEFAULT_BRANCH="${DEFAULT_BRANCH:-}"
if [ -z "$DEFAULT_BRANCH" ]; then
  echo "restore-default-branch-workflows.sh: DEFAULT_BRANCH is required" >&2
  exit 2
fi

if [ -n "${DEFAULT_REF:-}" ]; then
  ref="$DEFAULT_REF"
else
  ref="origin/${DEFAULT_BRANCH}"
  if ! git rev-parse --verify --quiet "$ref^{commit}" >/dev/null; then
    git fetch --depth=1 origin "$DEFAULT_BRANCH"
  fi
  if ! git rev-parse --verify --quiet "$ref^{commit}" >/dev/null; then
    echo "restore-default-branch-workflows.sh: could not resolve $ref" >&2
    exit 1
  fi
fi

# Check before deleting the working tree: git ls-tree exits 0 on a
# missing path and prints nothing, so an existence probe has to be
# cat-file, not ls-tree's status.
if ! git cat-file -e "$ref:.github/workflows" 2>/dev/null; then
  echo "restore-default-branch-workflows.sh: $ref has no .github/workflows tree" >&2
  exit 1
fi

# Drop the PR's workflow tree, including files the default branch does
# not have, then materialize the trusted copy.
rm -rf .github/workflows
mkdir -p .github
git checkout "$ref" -- .github/workflows
touch .github/workflows/.restored-from-default-branch

echo "Restored .github/workflows/ from $ref"
