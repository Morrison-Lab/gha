- **`WAIT_MAX_WORKERS` holds a new job while the host runs too many jobs at once**
  ([gha#1546](https://github.com/Morrison-Lab/gha/issues/1546)).
  When it is above 0, `scripts/wait-runner-capacity.sh` also waits until no more than that many `Runner.Worker` processes are running,
  within the same 10-minute cap.
  A Quarto render takes minutes to reach its full memory,
  so jobs that start together all pass the memory check and the host runs out of memory later.
  It is off by default, so existing runners are unaffected.
