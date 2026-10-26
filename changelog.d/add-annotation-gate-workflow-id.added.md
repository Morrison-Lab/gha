- **`annotation-gate-run.yml`: optional `workflow-id` input bounds the gate queue**
  ([Morrison-Lab/lds#1451](https://github.com/Morrison-Lab/lds/issues/1451)).
  Pass the finished run's `workflow_id` and `event`, joined, and a gate still queued or running
  for an earlier run of the same workflow on the same commit is cancelled
  when a newer one starts, so a burst of finishing runs cannot flood a small
  self-hosted runner pool.
  Callers that do not pass it are unchanged.
  The `examples/annotation-gate-run.yml` stub now passes it.
