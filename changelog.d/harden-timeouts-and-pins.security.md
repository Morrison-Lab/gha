- **Every job now sets `timeout-minutes`** (#328).
  49 jobs previously had no timeout, so a hung job ran to GitHub's six-hour
  default before the runner gave up.
  Values are deliberately generous (10 minutes for gate/dispatch jobs, 20 for
  checks and lints, 45 for builds and deploys, 60 for the agent workflows) --
  the point is catching a hang, not budgeting a run.
  Jobs that call a reusable workflow cannot set `timeout-minutes` themselves,
  so they inherit the timeout from the called workflow's own job.
- **`update-snapshots` pins its six remaining third-party actions to full
  commit SHAs** (#328).
  `r-lib/actions/pr-fetch`, `pr-push`, `setup-r`, `setup-r-dependencies`,
  `julia-actions/setup-julia`, and `julia-actions/cache` were pinned to tags,
  contradicting `README.md`'s statement that every third-party action is
  SHA-pinned.
  Every other call site of those actions in this repo already used the SHA
  form, so this was drift confined to one file -- and one whose job pushes
  commits, where a re-pointed tag matters most.
  `julia-actions/cache@v3` was a floating major tag; it is now pinned at the
  v3.1.0 commit it resolved to.
