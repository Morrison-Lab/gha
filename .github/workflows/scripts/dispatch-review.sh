#!/usr/bin/env bash
# Resolves PR_BRANCH / PR_HEAD_REPO if empty, determines whether --ref should be passed
# (omitting --ref for fork PRs or when PR_BRANCH cannot be resolved), and dispatches
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

if [[ -z "$PR_BRANCH" ]]; then
  echo "PR_BRANCH is empty from checkout step; attempting API lookup for PR #$PR_NUMBER."
  PR_BRANCH=$(gh api "repos/$REPO/pulls/$PR_NUMBER" --jq '.head.ref // empty' 2>/dev/null || true)
  PR_HEAD_REPO=$(gh api "repos/$REPO/pulls/$PR_NUMBER" --jq '.head.repo.full_name // empty' 2>/dev/null || true)
fi

NOTICE_SUFFIX=""
if [[ -n "$CONTEXT_NOTICE" ]]; then
  NOTICE_SUFFIX=" ($CONTEXT_NOTICE)"
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
  if [[ -n "$PR_HEAD_REPO" && "$PR_HEAD_REPO" != "$REPO" ]]; then
    echo "::notice::PR #$PR_NUMBER is from a fork ($PR_HEAD_REPO); dispatching $REVIEW_WF without --ref."
    REF_ARGS=()
  fi
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[dry-run] gh workflow run $REVIEW_WF ${REF_ARGS[*]:-} -f pr_number=$PR_NUMBER"
  else
    gh workflow run "$REVIEW_WF" "${REF_ARGS[@]}" -f pr_number="$PR_NUMBER" \
      || echo "::warning::Could not dispatch $REVIEW_WF$NOTICE_SUFFIX."
  fi
fi
