#!/usr/bin/env bash
# Resolves PR_BRANCH / PR_HEAD_REPO if empty, determines whether --ref should
# be passed (substituting --ref "$DEFAULT_BRANCH" when known, or omitting --ref,
# for fork PRs or when PR_BRANCH cannot be resolved --- gha#931; skipping review
# dispatch when the PR edits top-level workflow YAML to avoid preempting PR-head
# checks or attaching checks to the default branch --- gha#598, gha#921), and
# dispatches the review workflow via `gh workflow run`. (gha#419)
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
DEFAULT_BRANCH="${DEFAULT_BRANCH:-}"
DRY_RUN="${DRY_RUN:-false}"
IS_CLOSED="${IS_CLOSED:-false}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr-number) PR_NUMBER="$2"; shift 2 ;;
    --pr-branch) PR_BRANCH="$2"; shift 2 ;;
    --pr-head-repo) PR_HEAD_REPO="$2"; shift 2 ;;
    --review-workflow-file) REVIEW_WF="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --context-notice) CONTEXT_NOTICE="$2"; shift 2 ;;
    --default-branch) DEFAULT_BRANCH="$2"; shift 2 ;;
    --is-closed) IS_CLOSED="$2"; shift 2 ;;
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

if [[ "$IS_CLOSED" == "true" ]]; then
  echo "::notice::PR #$PR_NUMBER is closed or merged; skipping review dispatch."
  exit 0
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "$PR_BRANCH" ]]; then
  echo "PR_BRANCH is empty from checkout step; attempting API lookup for PR #$PR_NUMBER."
  info=$("$script_dir/resolve-pr-info.sh" --repo "$REPO" --pr-number "$PR_NUMBER")
  PR_BRANCH=$(echo "$info" | sed -n 's/^pr_branch=//p')
  PR_HEAD_REPO=$(echo "$info" | sed -n 's/^pr_head_repo=//p')
  is_closed=$(echo "$info" | sed -n 's/^is_closed=//p')
  if [[ "$is_closed" == "true" ]]; then
    echo "::notice::PR #$PR_NUMBER is closed or merged; skipping review dispatch."
    exit 0
  fi
fi

NOTICE_SUFFIX=""
if [[ -n "$CONTEXT_NOTICE" ]]; then
  NOTICE_SUFFIX=" ($CONTEXT_NOTICE)"
fi

# When the PR edits top-level workflow YAML, GitHub would execute the PR
# head's copy if we pass `--ref $PR_BRANCH`, while dispatching from the default
# branch registers check-runs against the default branch rather than the PR head
# and preempts the in-flight pull_request review (gha#598, gha#921).
# Skip review dispatch on workflow edits so the push-triggered pull_request review
# (which restores default-branch workflows after checkout) runs to completion on
# the PR head without being destroyed by a default-branch dispatch.
if [ -z "${PR_CHANGED_FILES+x}" ]; then
  if ! PR_CHANGED_FILES=$(REPO="$REPO" PR_NUMBER="$PR_NUMBER" bash "$script_dir/list-pr-changed-files.sh"); then
    echo "::notice::Could not list a complete file set for PR #$PR_NUMBER; skipping review dispatch to avoid executing untrusted workflow YAML or preempting PR-head checks (gha#598, gha#921)."
    PR_CHANGED_FILES=""
    FORCE_DEFAULT_BRANCH_WORKFLOWS=true
  fi
fi
workflow_edits=false
if [ "${FORCE_DEFAULT_BRANCH_WORKFLOWS:-false}" != "true" ]; then
  detect_out="$(PR_CHANGED_FILES="$PR_CHANGED_FILES" CALLER_WF_PATH="" bash "$script_dir/detect-pr-workflow-edits.sh")"
  workflow_edits="$(sed -n 's/^workflow_edits=//p' <<<"$detect_out")"
fi

if [[ "$workflow_edits" == "true" ]]; then
  echo "::notice::PR #$PR_NUMBER edits workflow files; skipping review dispatch because default-branch dispatches cannot attach status checks to the PR head and would preempt in-flight pull_request reviews (gha#921). Automatic review runs on push."
  exit 0
elif [[ "${FORCE_DEFAULT_BRANCH_WORKFLOWS:-false}" == "true" ]]; then
  echo "::notice::Could not verify whether PR #$PR_NUMBER edits workflow files; skipping review dispatch to avoid executing untrusted workflow YAML or preempting PR-head checks (gha#598, gha#921). Automatic review runs on push."
  exit 0
fi

if [[ -z "$PR_BRANCH" ]]; then
  REF_ARGS=()
  if [[ -n "$DEFAULT_BRANCH" ]]; then
    echo "::notice::PR_BRANCH could not be resolved; dispatching $REVIEW_WF from the default branch ($DEFAULT_BRANCH)."
    REF_ARGS=(--ref "$DEFAULT_BRANCH")
  else
    echo "::notice::PR_BRANCH could not be resolved; dispatching $REVIEW_WF without --ref."
  fi
  if [[ "$DRY_RUN" == "true" ]]; then
    if [[ ${#REF_ARGS[@]} -gt 0 ]]; then
      echo "[dry-run] gh workflow run $REVIEW_WF ${REF_ARGS[*]} -f pr_number=$PR_NUMBER"
    else
      echo "[dry-run] gh workflow run $REVIEW_WF -f pr_number=$PR_NUMBER"
    fi
  else
    gh workflow run "$REVIEW_WF" "${REF_ARGS[@]}" -f pr_number="$PR_NUMBER" \
      || echo "::warning::Could not dispatch $REVIEW_WF$NOTICE_SUFFIX."
  fi
else
  REF_ARGS=(--ref "$PR_BRANCH")
  if [[ "$PR_HEAD_REPO" != "$REPO" ]]; then
    REF_ARGS=()
    if [[ -n "$DEFAULT_BRANCH" ]]; then
      echo "::notice::PR #$PR_NUMBER is from a fork ($PR_HEAD_REPO); dispatching $REVIEW_WF from the default branch ($DEFAULT_BRANCH)."
      REF_ARGS=(--ref "$DEFAULT_BRANCH")
    else
      echo "::notice::PR #$PR_NUMBER is from a fork ($PR_HEAD_REPO); dispatching $REVIEW_WF without --ref."
    fi
  fi
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[dry-run] gh workflow run $REVIEW_WF ${REF_ARGS[*]:-} -f pr_number=$PR_NUMBER"
  else
    gh workflow run "$REVIEW_WF" "${REF_ARGS[@]}" -f pr_number="$PR_NUMBER" \
      || echo "::warning::Could not dispatch $REVIEW_WF$NOTICE_SUFFIX."
  fi
fi
