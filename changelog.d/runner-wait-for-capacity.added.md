- **A self-hosted runner now holds a new job at its start until the host has at least 3 GB of memory available and a load average under 1.25 per core** (#1509).
  `scripts/wait-runner-capacity.sh` runs after the disk check in the job-started hook,
  waits at most 10 minutes, and then lets the job run, so a busy host slows jobs down and never fails them.
  Three environment variables change the limits: `WAIT_MIN_MEM_GB`, `WAIT_MAX_LOAD_PER_CORE`, and `WAIT_MAX_MINUTES`.
  `WAIT_MAX_MINUTES=0` turns the wait off.
