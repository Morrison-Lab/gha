- **`claude-code-review` fails closed when there is no reviewed SHA**
  ([#679](https://github.com/Morrison-Lab/gha/issues/679)).
  On `workflow_dispatch`, `reviewed-head` is empty.
  If `gather-context` also failed, `stash-head` is empty too.
  Empty COMPARE previously skipped the mismatch arm, wrote
  `stale=false`, and the post-comment step fell back to live head.
  COMPARE now writes `stale=true` and exits before posting,
  `claude-review` does not start when `gather-context` failed,
  and the comment binds `COMMIT_SHA` to the compared SHA.
