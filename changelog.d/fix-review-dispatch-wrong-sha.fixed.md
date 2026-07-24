- **`claude.yml`'s and `claude-review.yml`'s `gh workflow run` dispatches of the
  review workflow now pass an explicit `--ref`** pointing at the PR's own head
  branch (#285). Without it, `workflow_dispatch` silently defaults the
  dispatched run's associated commit to the repository's default branch, so
  the resulting `require-review` check-run lands on the wrong SHA and never
  supersedes a stale, cancelled run tied to the PR's real head commit — a PR
  could show a fully clean, current review comment while its actual head
  commit's required-status-check view stayed red. The consumer-facing
  `examples/claude-code-review.yml` `/review`-comment dispatcher gets the same
  fix for consistency.
