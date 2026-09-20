- **`claude-code-review` resolves the reviewed commit once, so the
  review-data JSON's `commit_sha` names the PR head rather than GitHub's
  ephemeral merge ref** (#852). The model job now derives `REVIEWED_COMMIT`
  from `github.event.pull_request.head.sha`, falling back to the dispatch-path
  stash head that `post-review` already stale-checks against, and passes it
  to `run-claude-review-attempt` as a new `reviewed-commit` input; the prompt
  interpolates that one value into both `commit_sha` templates instead of
  leaving a placeholder the reviewer filled from `GITHUB_SHA`. The structured
  field and the trailing `Reviewed commit:` line therefore come from the same
  resolution and cannot disagree, and `run-review-job-split-tests.py` pins
  each hop, including that nothing hands the prompt `github.sha`.
