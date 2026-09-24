- **Review dispatch now skips PRs with workflow edits to prevent cancelling in-flight PR-head reviews** (#921).
  A manual or comment review dispatch on a workflow-editing PR previously ran on the default branch without `--ref`.
  Because GitHub Actions attaches check-runs to the commit SHA of the workflow run, default-branch dispatches land on `main` rather than the PR head.
  Concurrency group `cancel-in-progress` then preempted the push-triggered `pull_request` review, destroying the only review run whose check-runs could reach the PR head and satisfy branch protection.
  Review dispatchers across `dispatch-review.sh`, `claude-review.yml`, `ai-code-review.yml`, `claude.yml`, and `gemini.yml` now skip dispatch when a PR edits workflow files or has a truncated file list (comment and mention triggers post an explanatory PR comment, while workflow-internal dispatchers emit a runner notice).
  Review workflows now also isolate default-branch dispatches into a separate concurrency group, preventing accidental cancellations of PR-head review runs.
