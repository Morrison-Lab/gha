- `scripts/restart-runner-when-idle.sh` restarts a self-hosted runner between jobs,
  so it reloads `.env` and `.path` after a PATH change.
  It stops the listener with SIGTERM after it has run no job for ten seconds,
  because a listener started with `setsid nohup ./run.sh` ignores SIGINT.
  It relaunches only after the old listener has exited, and a lock stops two copies from restarting one runner,
  so it does not start a second listener beside the first.
