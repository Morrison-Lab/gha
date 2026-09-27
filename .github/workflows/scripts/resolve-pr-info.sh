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
DEFAULT_BRANCH="${DEFAULT_BRANCH:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr-number) PR_NUMBER="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --json-data) PR_JSON="$2"; shift 2 ;;
    --default-branch) DEFAULT_BRANCH="$2"; shift 2 ;;
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
pr_state=""
pr_merged=""
is_closed="false"
pr_base_branch=""
is_stacked="false"
if [[ -n "$PR_JSON" ]]; then
  pr_branch=$(jq -r '.head.ref // .branch // empty' <<< "$PR_JSON" 2>/dev/null || true)
  pr_head_repo=$(jq -r '.head.repo.full_name // .head_repo // empty' <<< "$PR_JSON" 2>/dev/null || true)
  pr_state=$(jq -r '.state // empty' <<< "$PR_JSON" 2>/dev/null || true)
  pr_merged=$(jq -r 'if .merged != null then (.merged | tostring) else empty end' <<< "$PR_JSON" 2>/dev/null || true)
  is_closed_field=$(jq -r 'if .closed != null then (.closed | tostring) else empty end' <<< "$PR_JSON" 2>/dev/null || true)
  pr_state_lower=$(echo "$pr_state" | tr '[:upper:]' '[:lower:]')
  pr_merged_lower=$(echo "$pr_merged" | tr '[:upper:]' '[:lower:]')
  if [[ "$pr_state_lower" == "closed" || "$pr_state_lower" == "merged" || "$pr_merged_lower" == "true" || "$is_closed_field" == "true" ]]; then
    is_closed="true"
  fi
  pr_base_branch=$(jq -r '.base.ref // empty' <<< "$PR_JSON" 2>/dev/null || true)
  repo_default_branch=$(jq -r '.base.repo.default_branch // empty' <<< "$PR_JSON" 2>/dev/null || true)
  effective_default="${DEFAULT_BRANCH:-$repo_default_branch}"
  if [[ -n "$pr_base_branch" && -n "$effective_default" && "$pr_base_branch" != "$effective_default" ]]; then
    is_stacked="true"
  fi
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
  echo "pr_state=$pr_state" >> "$GITHUB_OUTPUT"
  echo "pr_merged=$pr_merged" >> "$GITHUB_OUTPUT"
  echo "is_closed=$is_closed" >> "$GITHUB_OUTPUT"
  echo "pr_base_branch=$pr_base_branch" >> "$GITHUB_OUTPUT"
  echo "is_stacked=$is_stacked" >> "$GITHUB_OUTPUT"
fi

echo "pr_branch=$pr_branch"
echo "pr_head_repo=$pr_head_repo"
echo "is_fork=$is_fork"
echo "ref_arg=$ref_arg"
echo "pr_state=$pr_state"
echo "pr_merged=$pr_merged"
echo "is_closed=$is_closed"
echo "pr_base_branch=$pr_base_branch"
echo "is_stacked=$is_stacked"
