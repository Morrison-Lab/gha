- **`claude-code-review.yml`'s `post-review` now skips a superseded run that stashed no reviewers**
  (Morrison-Lab/lds#2979, a private repository the link checker cannot reach).
  GitHub keeps one pending job per concurrency group, and a new pending job cancels the one already waiting.
  So when a second review trigger arrived while the first run was queued,
  the old run's `post-review` entered the stash group and cancelled the new run's pending `gather-context`.
  Neither run then posted a review, and both failed with "no stash-head".
  A run whose `gather-context` or model job was cancelled now skips `post-review` unless it reported `stashed=true`.
  `stashed=true` is now written before the reviewer DELETE, so a run that removed reviewers always qualifies for its restore.
  A superseded run that did stash reviewers still enters the group, and can still cancel a newer pending `gather-context`,
  or have its own pending restore cancelled by one;
  both orders are tracked in [gha#2179](https://github.com/Morrison-Lab/gha/issues/2179).
