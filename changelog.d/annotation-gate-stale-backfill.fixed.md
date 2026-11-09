- **`annotation-gate-run.yml`: `backfill` also repairs a commit whose check is out of date.**
  A gate that defers posts nothing and relies on the last finishing run
  to start the gate that posts.
  When that `workflow_run` event never arrives after a re-run of cancelled jobs,
  the commit keeps the failure an earlier gate posted
  and blocks the pull request until someone dispatches the gate by hand
  (gha#1752, seen on lds#2170).
  With `backfill: true` the job now also gates a commit
  whose newest `annotation-gate` check run finished before a run on the commit did.
  Callers that do not pass `backfill` are unchanged.
