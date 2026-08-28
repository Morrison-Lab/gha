- **`check-news` now reads the PR's labels live, so a label applied after the
  triggering event still exempts** (#721, #722).
  Both the job-level `if` and the wrapped action previously read the labels
  frozen into the triggering event's payload;
  a label applied afterward (as `bump-dev-version` does to its own PR) was
  invisible there, and approving or re-running a gated run reuses the same
  stale payload -- so such a PR failed the changelog check while carrying the
  exemption label.
  A new fail-loud, case-insensitive live-label step is now the authority,
  matching both the configurable input label and the wrapped action's
  hardcoded "no changelog".
  **Consumer note:** the job now also requests `issues: read`;
  a caller that explicitly pins the calling job's `permissions` to
  `contents: read` alone must add `issues: read` or the workflow fails at
  startup requesting it.
  Callers with no explicit `permissions` block are unaffected.
  `version-check` has the same stale-payload defect, tracked separately
  (#722).
