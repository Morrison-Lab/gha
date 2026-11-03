- `scripts/restart-runner-when-idle.sh` restarts a self-hosted runner between jobs,
  so it reloads `.env` and `.path` after a PATH change.
  It stops the listener with SIGTERM once it holds no job,
  because a listener started with `setsid nohup ./run.sh` ignores SIGINT,
  and relaunches only after the old listener has exited,
  so the restart cannot leave two listeners competing for one runner session.
