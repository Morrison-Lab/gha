- `condor-batch` moves a job that does not start within `idle-minutes` to the next head in `head`,
  each with the same limit, and falls back to the runner only when no head starts it (gha#2087).
  Each run logs the head that took the job and how many seconds it sat in the queue.
