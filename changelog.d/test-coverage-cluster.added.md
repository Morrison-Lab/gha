- **`cluster-check` job on `test-coverage.yml`**, off by default,
  measures coverage on a WWU cluster node through `condor-batch`
  and skips the runner job.
  It adds the inputs `cluster-runs-on`, `cluster-head`, `cluster-image`, and `cluster-image-file`.
  It writes the Cobertura report and the percent to the `cluster-coverage` artifact,
  applies `min-coverage`, and does not upload to Codecov (gha#1640).
