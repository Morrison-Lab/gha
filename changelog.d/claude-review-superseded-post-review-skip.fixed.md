- **`claude-code-review.yml`'s `post-review` now skips a superseded run whose `gather-context` was cancelled before it stashed reviewers**
  ([Morrison-Lab/lds#2979](https://github.com/Morrison-Lab/lds/issues/2979)).
  GitHub keeps one pending job per concurrency group, and a new pending job cancels the one already waiting.
  So when a second review trigger arrived while the first run was queued,
  the old run's `post-review` entered the stash group and cancelled the new run's pending `gather-context`.
  Neither run then posted a review, and both failed with "no stash-head".
  A cancelled `gather-context` that did stash reviewers still runs `post-review`, so those reviewers are restored.
