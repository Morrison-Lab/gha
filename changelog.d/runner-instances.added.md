- **`scripts/register-self-hosted-runner.sh`** --
  takes `RUNNER_INSTANCES=<n>` to set up n runners on one host,
  each in its own directory (`<RUNNER_DIR>-2`, ...) and named `<RUNNER_NAME>-2`, ...,
  so jobs no longer queue behind a single runner.
