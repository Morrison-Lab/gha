- **`WAIT_MAX_BLOCKED` holds a new job while the host has processes blocked on disk I/O**
  ([gha#1527](https://github.com/Morrison-Lab/gha/issues/1527)).
  When it is above 0, `scripts/wait-runner-capacity.sh` also waits until fewer than that many processes are blocked (`procs_blocked` in `/proc/stat`),
  within the same 10-minute cap.
  A host with a slow disk can show a low load average while renders stall on writes,
  so the load limit alone does not hold the next job back.
  It is off by default, so existing runners are unaffected.
