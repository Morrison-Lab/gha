- **`run-review-job-split-tests.py` guards against a repo-relative script
  path in a checkout-less job** (#812).
  gha#813 fixed the one step that had one; this asserts the shape cannot
  recur elsewhere in `claude-code-review.yml`.
  A reusable workflow's steps run against the caller's tree, and
  `post-review` checks nothing out at all, so such a path cannot resolve --
  it exited 127 after the review comment had already posted.
  The script's own unit suite cannot see this, since it supplies its own
  path from a job that does check the repo out.
