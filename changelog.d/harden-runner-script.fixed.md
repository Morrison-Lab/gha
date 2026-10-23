- **`scripts/register-self-hosted-runner.sh`** --
  passes the registration token to the runner through its environment
  instead of its command line,
  where other users of the host could read it.
  It also refuses a runner group whose visibility is `all`,
  checks the group again before it starts an already-configured runner,
  stops on a download or checksum failure with a clear message,
  and documents the Team-plan requirement
  ([#1167](https://github.com/Morrison-Lab/gha/issues/1167)).
