- The job-started hook `scripts/check-runner-disk.sh` now empties the job's
  `<work>/<repo>/<repo>` workspace before `actions/checkout` runs.
  A reused tree had left checkouts half switched,
  so checks failed on files the commit holds (Morrison-Lab/lds#3292).
  Set `CHECK_DISK_KEEP_WORKSPACE=1` in the runner's `.env` to keep the tree.
  The change reaches a runner once its host's gha checkout is fast-forwarded.
