- **`WAIT_MAX_WORKERS` no longer holds a burst of jobs until the deadline**
  ([gha#1549](https://github.com/Morrison-Lab/gha/issues/1549)).
  A held job is itself a `Runner.Worker`, so every job in a burst counted the others and all waited the full `WAIT_MAX_MINUTES`.
  Held jobs now take a ticket and are not counted as running,
  and a job starts when the running jobs plus the older tickets are fewer than the limit, so a burst drains oldest first.
  The worker pattern is also anchored to the worker's executable
  ([gha#1551](https://github.com/Morrison-Lab/gha/issues/1551)),
  and the hold message names the limit and the running count
  ([gha#1550](https://github.com/Morrison-Lab/gha/issues/1550)).
