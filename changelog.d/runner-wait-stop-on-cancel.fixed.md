- **`wait-runner-capacity.sh` stops holding a job when the runner cancels it, and holds for 4 minutes by default instead of 10**
  ([gha#1582](https://github.com/Morrison-Lab/gha/issues/1582)).
  A job with a 5-minute `timeout-minutes` could sit in "Set up runner" until the timeout cancelled it,
  and the hook ignored the cancel and kept waiting for another 5 minutes.
  The hook now exits at once on a termination signal,
  and its default `WAIT_MAX_MINUTES` is under the 5-minute timeout of the shortest checks.
  A runner that sets `WAIT_MAX_MINUTES` in its `.env` keeps its value.
