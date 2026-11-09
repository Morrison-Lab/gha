- Add `report-main-failure.yml`, a reusable workflow for a `workflow_run`
  caller stub that follows up when a workflow fails on the default branch.
  It ignores cancelled runs, re-runs a failure that looks like infrastructure
  once, and otherwise files or updates one issue per workflow, labelled
  `infra-suspect` when the re-run also looks like infrastructure. See
  `examples/report-main-failure.yml`
  ([#1770](https://github.com/Morrison-Lab/gha/issues/1770)).
