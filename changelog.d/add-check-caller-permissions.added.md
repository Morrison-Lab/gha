- `check-caller-permissions`:
  add a blocking composite action and reusable workflow that fails when a workflow
  calls a `Morrison-Lab/gha` reusable workflow from a job that does not grant the
  permissions the callee's jobs request
  (lds#1468).
  GitHub rejects such a call at startup (`startup_failure`) before any step runs,
  so a scheduled caller stopped silently for a week.
  The check fetches each callee at the ref the caller pins and compares the union of its
  jobs' permissions with the calling job's grant, or the workflow-level block.
  A call with no block at either level is reported as unchecked, not clean.
  It runs in the consumer repository and needs no cross-repository token.
