- **`update-snapshots` can push with a `WORKFLOW_TOKEN` secret, so the
  snapshot commit gets CI** (Morrison-Lab/bcs#1110).
  A push made with `GITHUB_TOKEN` starts no workflow runs, so the pushed
  commit became the PR head with no checks on it.
  The new optional secret is used for the push when the caller passes it;
  without it, or when pushing with it fails, the workflow pushes with
  `GITHUB_TOKEN` as before and posts a warning naming the commit that has
  no CI.
  The push now runs in a separate `push` job that runs none of the
  branch's code, so the token is never exposed to the tests (in `pr-mode`
  possibly a fork PR's), and the test job drops to `contents: read`.
  That job pushes only a single commit on the branch's current head that
  changes nothing outside `tests/testthat/_snaps/`.
  Both modes now push with plain `git push` rather than
  `r-lib/actions/pr-push`, which also calls the pulls API and so would
  need a pull-request scope on the token.
- **`update-snapshots` no longer stops accepting snapshots after 10
  failures** (Morrison-Lab/bcs#1110).
  testthat's progress reporter quits at 10 failures by default, so a change
  touching more snapshots than that never reached the rest, and the
  verification pass then failed with nothing committed.
  The test step now sets `TESTTHAT_MAX_FAILS=Inf`.
- **`update-snapshots` moves to `@v3`.**
  `@v2` is frozen, so the `WORKFLOW_TOKEN` secret and the separate `push`
  job exist only at `@v3`; a caller still on `@v2` that passes the secret
  fails with an unknown-secret error.
  The caller stub, the reference page and the versioning lists now pin
  `@v3`.
