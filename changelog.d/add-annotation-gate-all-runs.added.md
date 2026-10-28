- **`annotation-gate-run.yml`: `all-runs` input gates a whole commit in one job.**
  With `all-runs: true` the job lists the commit's workflow runs,
  gates the newest completed run of each workflow and event,
  and posts one `annotation-gate` check run.
  A caller that also sets a workflow-level `concurrency` group per commit
  queues one gate for a burst of finishing runs, not one per workflow,
  so a small self-hosted pool is not flooded.
  The commit carries one check of that name, not one per workflow.
  Callers that do not pass it are unchanged.
  The `examples/annotation-gate-run.yml` stub now uses it.
