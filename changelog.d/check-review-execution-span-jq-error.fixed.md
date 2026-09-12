- `claude-code-review.yml`: fail fast when jq span extraction throws an error
  in `check-review-execution.sh` (#861).
  A runtime error in jq during assistant-block span extraction is now caught
  with `failure_kind=hard-error` and logged as an error annotation rather than
  discarding stderr and exiting 0 with an empty posted review comment.
