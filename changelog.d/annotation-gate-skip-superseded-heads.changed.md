- `annotation-gate-run.yml` skips a run on a pull request's superseded head before it takes a runner.
  The `workflow_run` payload's `pull_requests[0].head.sha` is the PR's current head,
  so a run whose own head differs gates a commit no one will merge.
  On 2026-11-19 such gates were 41 of about 500 queued lds runs (Morrison-Lab/lds#2992).
