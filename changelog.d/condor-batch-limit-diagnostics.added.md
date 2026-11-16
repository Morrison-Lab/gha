- `condor-batch` now prints why a job did not end when `wait-minutes` expires:
  `condor_q -better-analyze` for the cluster, `condor_status -total`, and the tail of `condor.log`, before it removes the job.
  The queue entry and the run directory are gone by the time anyone looks, so the cause of a stalled cluster was not recoverable (gha#2041).
  A failing diagnostic does not stop the fallback to the runner.
