- `check-div-ids`:
  fail by default instead of warning (Ezra, 2026-11-04; gha#1459).
  The `fail` input default changes from `false` to `true`, in the action and the reusable workflow;
  the check is diff-scoped, so only newly added lines fail.
  A caller that wants warnings sets `fail: false`.
