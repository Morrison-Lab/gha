- **`scripts/register-self-hosted-runner.sh`** --
  takes `RUNNER_INSTANCES=<n>` to set up n runners on one host,
  each in its own directory (`<RUNNER_DIR>-2`, ...) and named `<RUNNER_NAME>-2`, ...,
  so jobs no longer queue behind a single runner.
  The default `RUNNER_DIR` is now `~/actions-runner-private-<host>`,
  so two hosts that share an NFS home do not share a runner;
  a runner already in `~/actions-runner-private` keeps working there.
  New runners check out into a local work folder,
  `RUNNER_WORK_DIRECTORY` (default `/var/tmp/gha-work/<runner name>`),
  because on NFS a shallow clone took 10 s against 0.6 s locally.
  `INSTALL_REBOOT_CRON=1` adds one `@reboot` crontab line that reruns the script
  (replaced, not duplicated, on a rerun),
  and `DRY_RUN_CONFIG=1` prints the names and directories a run would use.
