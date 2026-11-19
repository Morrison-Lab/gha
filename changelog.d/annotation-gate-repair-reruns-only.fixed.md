- `annotation-gate`: the repair pass now checks only commits whose watched workflow was re-run (`run_attempt` above 1),
  since a first attempt's own completion already gated its commit.
  Checking every recently finished commit on each gate used up Morrison-Lab/lds's hourly `GITHUB_TOKEN` quota
  within about 20 minutes of each reset.
