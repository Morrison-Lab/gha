- **`claude-code-review` fails closed when there is no reviewed SHA**
  ([#679](https://github.com/Morrison-Lab/gha/issues/679)).
  On `workflow_dispatch`, `reviewed-head` is empty.
  If `gather-context` also failed, `stash-head` is empty too.
  Empty COMPARE previously skipped the mismatch arm, wrote
  `stale=false`, and the post-comment step fell back to live head.
  COMPARE now writes `stale=true` and exits before posting when
  the model ran, so `require-review` goes red rather than gray.
  The comment binds `COMMIT_SHA` to the compared SHA.
  Consumer docs now match gha#585: a cancelled review skips
  `require-review` gray; an unbound SHA does not.
