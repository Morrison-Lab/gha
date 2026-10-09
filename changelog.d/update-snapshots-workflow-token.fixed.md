- **`update-snapshots` can push with a `WORKFLOW_TOKEN` secret, so the
  snapshot commit gets CI** (Morrison-Lab/bcs#1110).
  A push made with `GITHUB_TOKEN` starts no workflow runs, so the pushed
  commit became the PR head with no checks on it.
  The new optional secret is used for the push when the caller passes it;
  without it the workflow pushes as before and posts a warning naming the
  commit that has no CI.
  Both modes now push with plain `git push` rather than
  `r-lib/actions/pr-push`, which also calls the pulls API and so would
  need a pull-request scope on the token.
- **`update-snapshots` no longer stops accepting snapshots after 10
  failures** (Morrison-Lab/bcs#1110).
  testthat's progress reporter quits at 10 failures by default, so a change
  touching more snapshots than that never reached the rest, and the
  verification pass then failed with nothing committed.
  The test step now sets `TESTTHAT_MAX_FAILS=Inf`.
