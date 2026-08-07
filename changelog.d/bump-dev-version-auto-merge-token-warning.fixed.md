- **`bump-dev-version` warns when `auto-merge` cannot complete** (#409).
  A `GITHUB_TOKEN`-authored bump PR does not trigger the `pull_request` runs
  that required status checks need, so in a repo with required checks native
  `auto-merge` waits on conditions that never arrive and the PR sits open on
  every merge.
  The reusable workflow now emits a `::warning::` at the start of its run when
  `auto-merge` is on and `WORKFLOW_TOKEN` is unset, and the caller stub and
  reference page document that `WORKFLOW_TOKEN` is effectively required in that
  case (it authors the PR as a real user, whose `pull_request` runs are not
  suppressed).
