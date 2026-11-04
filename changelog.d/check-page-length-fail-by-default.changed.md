- `check-page-length`:
  fail by default instead of warning (Ezra, 2026-11-04; gha#1475).
  The `fail` input default changes from `false` to `true`, in the action and the reusable workflow;
  the check is diff-scoped, so only pages a PR adds to can fail.
  A caller that wants warnings sets `fail: false`.
