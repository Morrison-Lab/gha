- **Document that GitHub suppresses `pull_request` workflow runs on conflicting PRs** (#859).
  When a pull request has merge conflicts with its base branch, GitHub
  Actions runs no `pull_request` workflows on push or ready events.
  The documentation in `claude-code-review.yml`, `examples/claude-code-review.yml`,
  `website/reference/claude-code-review.qmd`, and `CLAUDE.md` now details this
  platform behavior and notes that `workflow_dispatch` can be used to trigger
  reviews on conflicting heads.
