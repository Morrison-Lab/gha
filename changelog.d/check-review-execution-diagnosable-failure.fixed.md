- **`check-review-execution` and failure reports point to step error logs on action failure** (#906).
  When Claude review produces no execution output due to the action exiting non-zero, error
  annotations and failure reports now explicitly point to the `Run Claude Code Review` step
  log so diagnosable causes (such as an unpermitted bot actor in `allowed_bots` or setup failures)
  are not mistaken for intermittent execution short-circuits.
