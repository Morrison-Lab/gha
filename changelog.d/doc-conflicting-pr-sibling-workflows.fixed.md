- **Document conflicting PR `pull_request` suppression across sibling workflows** (#892).
  GitHub Actions does not trigger `pull_request` workflow runs
  when a pull request has merge conflicts with its base branch.
  Documented this platform behavior across sibling review workflows
  (`gemini-code-review.yml`,
  `antigravity-code-review.yml`,
  `cursor-code-review.yml`,
  `opencode-code-review.yml`,
  and `ai-code-review.yml`),
  their example caller stubs,
  and their corresponding reference pages in `website/reference/`,
  noting that reviews on conflicting PRs can still be triggered
  via `workflow_dispatch` or by resolving conflicts.
