- `wait-runner-capacity.sh` no longer holds a job on a runner named like
  `private-gate-*` (set `WAIT_SKIP_RUNNER_NAMES` to change the globs),
  so the near-instant gate jobs do not each wait up to 2 minutes
  behind the builds on their host (gha#1729).
