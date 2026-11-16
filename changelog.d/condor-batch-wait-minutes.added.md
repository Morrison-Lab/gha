- `condor-batch` takes a `wait-minutes` input (`CONDOR_WAIT_MINUTES`) that limits the wait for the cluster job.
  A job that has not ended by then is removed with `condor_rm`, and the steps rerun on the runner.
  Set it below the caller's `timeout-minutes`.
  Without it, a job stuck in the queue ran into the job timeout,
  which cancelled the step before the fallback could run (gha#2037).
  Empty, the default, keeps the old unbounded wait.
