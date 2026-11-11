- `claude-code-review.yml`'s `require-clean-verdict` no longer stays red when a newer review run of the same head is clean ([gha#1365](https://github.com/Morrison-Lab/gha/issues/1365)).
  When its own run's verdict is not clean, it now looks up the reviews posted on the PR, through the new internal composite `find-newer-review-verdict`.
  It passes when the newest review of that head comes from a newer run and reads as clean.
  Re-running the older run's failed jobs now clears its check without paying for a new review.
  The gate job now requests `pull-requests: read`, which `find-fallback-verdict` already requests, so callers need no new grant.
  `post-review` gains a `reviewed_sha` output.
