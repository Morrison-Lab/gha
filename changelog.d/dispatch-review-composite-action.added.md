- **Extract `dispatch-review` into a shared composite action** ([#419](https://github.com/Morrison-Lab/gha/issues/419)).
  Encapsulates `PR_BRANCH` resolution, GitHub API fallback, and fork-aware
  `--ref` dispatch logic into `.github/actions/dispatch-review` wrapping
  `.github/workflows/scripts/dispatch-review.sh`, with offline unit test coverage.
