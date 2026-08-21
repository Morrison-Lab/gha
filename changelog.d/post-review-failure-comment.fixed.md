- `claude-code-review`: post a comment when a review run finishes without a
  usable verdict, instead of leaving the pull request thread silent
  ([#543](https://github.com/Morrison-Lab/gha/issues/543)).
  Every posting step was gated on `Resolve final review outcome` having
  succeeded, so a no-verdict review skipped the quota notice, the review
  comment, the cost comment, and the collapse step together.
  The run still spent money and still reddened `require-review`, but from the
  thread it was indistinguishable from a reviewer that had not started yet.
  The new comment names the failure, the denied tools, and the cost, and links
  the run.
- `claude-code-review`: record the cost of a review that produced no verdict.
  It was written only on the paths where a review succeeded, so the spend on
  exactly the runs that wasted it was the spend that went unrecorded.
- `check-review-execution.sh`: add `failure_kind`, `denied_tools`, and
  `max_denials` outputs.
  The denied tool names reached the job log and an annotation in
  [#544](https://github.com/Morrison-Lab/gha/pull/544) but never the pull
  request; carrying them to the thread is what makes a recurrence of
  [#198](https://github.com/Morrison-Lab/gha/issues/198)'s signature
  answerable without downloading an execution artifact.
