- `condor-batch` gains `idle-minutes` (`CONDOR_IDLE_MINUTES`):
  a cluster job still idle in the queue after that many minutes is removed,
  with `condor_q -better-analyze` printed first, and the steps run on the runner.
  A job that has started is never cut off.
  `preview` passes it as `cluster-idle-minutes`, default 20,
  so a busy pool costs a preview 20 minutes instead of the whole job timeout (gha#2085).
