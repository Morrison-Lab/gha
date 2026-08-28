- `claude-code-review.yml`: the posting job now fails closed when it has no
  reviewed SHA to bound the review to a commit (#679).
  On `workflow_dispatch` there is no event-pinned head,
  and a failed `gather-context` leaves no stash-head either;
  previously that empty comparison skipped the stale test,
  wrote `stale=false`,
  and stamped the posted comment with a live-head API fetch --
  an unverifiable review naming a commit the model may never have read.
  The `claude-review` job's `if:` now also excludes a failed
  `gather-context`,
  the posted comment stamps exactly the SHA the stale test bounded
  (no live-head fallback),
  and the consumer reference page catches up with gha#585
  (a cancelled superseded review skips the `require-review` gate gray
  rather than turning it red,
  and the gray list now includes the stale-post case).
  The job-split suite pins each of these,
  plus the pack/download artifact-name parity,
  `require-review` sitting in neither concurrency group,
  and `denied_tools` never being interpolated into a `run:` body (gha#541).
