- **`annotation-gate-run.yml`: gate a finished run from a `workflow_run`
  workflow**
  ([#1099](https://github.com/Morrison-Lab/gha/issues/1099)).
  A repository whose checks are spread over many workflow files gates each
  run that finishes, and the result is posted as an `annotation-gate` check
  run on that run's commit.
  The `annotation-gate` action gained `run-id`, `run-attempt` and `head-sha`
  inputs; callers of the existing `annotation-gate.yml` are unchanged.
  The workflow works only after `v3` slides past this change: before that,
  the action ignores the new inputs and gates its own run.
