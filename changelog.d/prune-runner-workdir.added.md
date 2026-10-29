- **Self-hosted runners prune old checkouts after each job** --
  `scripts/register-self-hosted-runner.sh` now installs `scripts/prune-runner-workdir.sh`
  as each runner's job-completed hook (via the new `scripts/install-runner-cleanup-hook.sh`).
  The hook deletes checkouts no job has used for 7 days,
  and the oldest others while under 10 GB is free,
  never the current job's checkout or the runner's own `_*` folders.
  The runner never removes a checkout itself,
  and three runners filled a 28 GB disk in six days
  ([#1352](https://github.com/Morrison-Lab/gha/issues/1352)).
