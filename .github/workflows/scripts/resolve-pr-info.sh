#!/usr/bin/env bash
# Resolves PR head branch, head repo, fork status, and --ref argument over API. (gha#369)
set -euo pipefail

if [[ "${1:-}" == "--self-test" ]]; then
  shift
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  exec "$script_dir/tests/run-resolve-pr-info-tests.sh" "$@"
fi

PR_NUMBER="${PR_NUMBER:-}"
REPO="${GH_REPO:-${REPO:-}}"
PR_JSON="${PR_JSON:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr-number) PR_NUMBER="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --json-data) PR_JSON="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$PR_JSON" ]]; then
  if [[ -z "$PR_NUMBER" || -z "$REPO" ]]; then
    echo "::error::resolve-pr-info: PR_NUMBER and REPO are required when JSON data is not provided." >&2
    exit 1
  fi
  PR_JSON=$(gh api "repos/$REPO/pulls/$PR_NUMBER" 2>/dev/null || true)
fi

pr_branch=""
pr_head_repo=""
if [[ -n "$PR_JSON" ]]; then
  pr_branch=$(jq -r '.head.ref // .branch // empty' <<< "$PR_JSON" 2>/dev/null || true)
  pr_head_repo=$(jq -r '.head.repo.full_name // .head_repo // empty' <<< "$PR_JSON" 2>/dev/null || true)
fi

is_fork="false"
if [[ -n "$pr_head_repo" && -n "$REPO" && "$pr_head_repo" != "$REPO" ]]; then
  is_fork="true"
fi

ref_arg=""
if [[ "$is_fork" == "false" && -n "$pr_branch" ]]; then
  ref_arg="--ref $pr_branch"
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "pr_branch=$pr_branch" >> "$GITHUB_OUTPUT"
  echo "pr_head_repo=$pr_head_repo" >> "$GITHUB_OUTPUT"
  echo "is_fork=$is_fork" >> "$GITHUB_OUTPUT"
  echo "ref_arg=$ref_arg" >> "$GITHUB_OUTPUT"
fi

echo "pr_branch=$pr_branch"
echo "pr_head_repo=$pr_head_repo"
echo "is_fork=$is_fork"
echo "ref_arg=$ref_arg"
