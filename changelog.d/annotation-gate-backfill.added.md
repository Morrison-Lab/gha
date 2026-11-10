- **`annotation-gate-run.yml`: `backfill` input repairs a commit that never got its check.**
  A gate that defers posts nothing and relies on the last finishing run
  to start the gate that posts.
  When that `workflow_run` event never arrives, the commit has no `annotation-gate` check run,
  the required check is missing, and GitHub blocks the pull request with nothing to re-run
  (gha#1754, seen on lds#2125).
  With `backfill: true` the job gates each commit that a pull request run touched in the last 24 hours
  and that has no `annotation-gate` check run,
  and leaves a commit with a run still queued or in progress to that run's own gate.
  A scheduled caller runs it beside the `workflow_run` gate.
  It reads runs and check runs only, so the workflow's permissions are unchanged.
  Callers that do not pass it are unchanged.
