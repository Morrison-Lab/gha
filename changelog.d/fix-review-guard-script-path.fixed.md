- **`claude-code-review.yml`'s fail-check guard no longer fails with
  "No such file or directory" on every consumer repo** (#190). #176 extracted
  the guard logic into `scripts/check-review-execution.sh` and referenced it
  as `${GITHUB_WORKSPACE}/.github/workflows/scripts/check-review-execution.sh`
  — but `GITHUB_WORKSPACE` holds the *caller's* checkout in a `workflow_call`
  run, not `d-morrison/gha`'s own tree, so the script was missing for every
  consumer repo (surfaced via
  [UCD-SERG/serodynamics#193](https://github.com/UCD-SERG/serodynamics/pull/193)).
  The guard step now checks out the script from this reusable workflow's own
  repo/ref (resolved via `github.job_workflow_ref`) into a side directory
  before running it.
