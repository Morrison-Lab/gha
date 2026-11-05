- **Self-hosted runners fail a job early when the disk is short** --
  `scripts/check-runner-disk.sh` is installed as the runner's job-started hook
  (by `scripts/install-runner-cleanup-hook.sh`).
  It sweeps stale temp folders, then fails the job with the free space and the largest folders
  when under 5 GB is free
  ([#1495](https://github.com/Morrison-Lab/gha/issues/1495)).
