#!/usr/bin/env bash
# Resolves PR_BRANCH / PR_HEAD_REPO if empty, determines whether --ref should
# be passed (omitting --ref for fork PRs, when PR_BRANCH cannot be resolved,
# or when the PR edits top-level workflow YAML so GitHub executes the
# default-branch caller rather than the PR head --- gha#598), and dispatches
# the review workflow via `gh workflow run`. (gha#419)
set -euo pipefail

if [[ "${1:-}" == "--self-test" ]]; then
  shift
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  exec "$script_dir/tests/run-dispatch-review-tests.sh" "$@"
fi

PR_NUMBER="${PR_NUMBER:-}"
PR_BRANCH="${PR_BRANCH:-}"
PR_HEAD_REPO="${PR_HEAD_REPO:-}"
REVIEW_WF="${REVIEW_WF:-claude-code-review.yml}"
REPO="${GH_REPO:-${REPO:-}}"
CONTEXT_NOTICE="${CONTEXT_NOTICE:-}"
DRY_RUN="${DRY_RUN:-false}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr-number) PR_NUMBER="$2"; shift 2 ;;
    --pr-branch) PR_BRANCH="$2"; shift 2 ;;
    --pr-head-repo) PR_HEAD_REPO="$2"; shift 2 ;;
    --review-workflow-file) REVIEW_WF="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --context-notice) CONTEXT_NOTICE="$2"; shift 2 ;;
    --dry-run) DRY_RUN="true"; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$PR_NUMBER" ]]; then
  echo "::error::dispatch-review: PR_NUMBER is required." >&2
  exit 1
fi

if [[ -z "$REPO" ]]; then
  echo "::error::dispatch-review: GH_REPO / REPO is required." >&2
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "$PR_BRANCH" ]]; then
  echo "PR_BRANCH is empty from checkout step; attempting API lookup for PR #$PR_NUMBER."
  info=$("$script_dir/resolve-pr-info.sh" --repo "$REPO" --pr-number "$PR_NUMBER")
  PR_BRANCH=$(echo "$info" | sed -n 's/^pr_branch=//p')
  PR_HEAD_REPO=$(echo "$info" | sed -n 's/^pr_head_repo=//p')
fi

NOTICE_SUFFIX=""
if [[ -n "$CONTEXT_NOTICE" ]]; then
  NOTICE_SUFFIX=" ($CONTEXT_NOTICE)"
fi

# When the PR edits top-level workflow YAML, GitHub would execute the PR
# head's copy if we pass `--ref $PR_BRANCH`. Omit --ref so the default
# branch's caller runs instead --- trusted YAML, and the review job
# checkouts the PR head for the code. (gha#598)
if [ -z "${PR_CHANGED_FILES+x}" ]; then
  if ! PR_CHANGED_FILES=$(REPO="$REPO" PR_NUMBER="$PR_NUMBER" bash "$script_dir/list-pr-changed-files.sh"); then
    echo "::notice::Could not list a complete file set for PR #$PR_NUMBER; dispatching $REVIEW_WF without --ref so GitHub executes default-branch workflow YAML."
    PR_CHANGED_FILES=""
    FORCE_DEFAULT_BRANCH_WORKFLOWS=true
  fi
fi
workflow_edits=false
if [ "${FORCE_DEFAULT_BRANCH_WORKFLOWS:-false}" != "true" ]; then
  detect_out="$(PR_CHANGED_FILES="$PR_CHANGED_FILES" CALLER_WF_PATH="" bash "$script_dir/detect-pr-workflow-edits.sh")"
  workflow_edits="$(sed -n 's/^workflow_edits=//p' <<<"$detect_out")"
fi

if [[ -z "$PR_BRANCH" ]]; then
  echo "::notice::PR_BRANCH could not be resolved; dispatching $REVIEW_WF without --ref."
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[dry-run] gh workflow run $REVIEW_WF -f pr_number=$PR_NUMBER"
  else
    gh workflow run "$REVIEW_WF" -f pr_number="$PR_NUMBER" \
      || echo "::warning::Could not dispatch $REVIEW_WF$NOTICE_SUFFIX."
  fi
else
  REF_ARGS=(--ref "$PR_BRANCH")
  if [[ "$PR_HEAD_REPO" != "$REPO" ]]; then
    echo "::notice::PR #$PR_NUMBER is from a fork ($PR_HEAD_REPO); dispatching $REVIEW_WF without --ref."
    REF_ARGS=()
  fi
  if [[ "$workflow_edits" == "true" ]]; then
    echo "::notice::PR #$PR_NUMBER edits workflow files; dispatching $REVIEW_WF from the default branch so GitHub executes trusted workflow YAML rather than the PR head (gha#598)."
    REF_ARGS=()
  elif [[ "${FORCE_DEFAULT_BRANCH_WORKFLOWS:-false}" == "true" ]]; then
    REF_ARGS=()
  fi
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[dry-run] gh workflow run $REVIEW_WF ${REF_ARGS[*]:-} -f pr_number=$PR_NUMBER"
  else
    gh workflow run "$REVIEW_WF" "${REF_ARGS[@]}" -f pr_number="$PR_NUMBER" \
      || echo "::warning::Could not dispatch $REVIEW_WF$NOTICE_SUFFIX."
  fi
fi
