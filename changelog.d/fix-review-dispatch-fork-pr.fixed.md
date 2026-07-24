- **Review-workflow dispatches (`claude.yml`, `claude-review.yml`,
  `examples/claude-code-review.yml`) now skip `--ref` for fork-originated
  PRs** (#289). `.head.ref` is just the branch name with no owner prefix, so
  for a fork PR it names a branch that generally doesn't exist in this repo
  -- passing it to `gh workflow run --ref` would fail to resolve and, in
  `claude-review.yml`'s `/review`-comment dispatcher specifically, hard-fail
  the whole job (no `|| echo "::warning::..."` fallback there). Each dispatch
  site now compares the PR's head repo against the base repo and falls back
  to dispatching without `--ref` for a fork PR, accepting the pre-#285
  wrong-SHA-attribution behavior as the lesser problem rather than failing
  the dispatch outright.
