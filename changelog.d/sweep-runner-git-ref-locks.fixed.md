- **The runner job-completed hook** also removes stale ref locks under a checkout's `.git/refs`.
  A killed fetch left `refs/remotes/origin/<branch>.lock`,
  which the sweep did not reach,
  so the next checkout on that runner failed with "cannot lock ref" (gha#1716).
