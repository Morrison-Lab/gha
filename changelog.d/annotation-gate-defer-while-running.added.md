- **`annotation-gate`: `defer-while-running` input skips a gate while the commit still has a run in flight.**
  With `all-runs: true` and `defer-while-running: true`,
  a gate that finds another workflow's run on the commit still queued or in progress
  exits without fetching annotations or posting a check run;
  that run's completion starts its own gate, so the last to finish gates the commit.
  A burst of workflows finishing together then leaves one gate that does the work (gha#1307).
  Off by default: a quick failure is then reported only when the slowest workflow on the commit finishes.
