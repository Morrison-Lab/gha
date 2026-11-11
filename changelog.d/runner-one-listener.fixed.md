- **A self-hosted runner can no longer get two listeners** --
  the new `scripts/run-runner-exclusive.sh` starts `run.sh` only when no other start holds the runner's `.listener.lock`
  and no `Runner.Listener` from that directory is running, and names the PID when it refuses.
  The systemd unit, `register-self-hosted-runner.sh`, and `restart-runner-when-idle.sh` all start the runner through it
  ([#1370](https://github.com/Morrison-Lab/gha/issues/1370)).
