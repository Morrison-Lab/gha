- `annotation-gate`: the repair pass now checks only commits whose watched workflow was re-run (`run_attempt` above 1),
  since a first attempt's own completion starts a gate
  (a first attempt whose event is lost, or whose gate fails, is left to the scheduled backfill).
  Checking every recently finished commit on each gate used up Morrison-Lab/lds's hourly `GITHUB_TOKEN` quota
  within about 20 minutes of each reset.
