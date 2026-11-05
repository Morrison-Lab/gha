- `check-write-idiom`:
  fail by default instead of warning (Ezra, 2026-11-04; gha#1472).
  The `fail` input default changes from `false` to `true`, in the action and the reusable workflow;
  the check is diff-scoped, so only newly added lines fail.
  A caller that wants warnings sets `fail: false`.
  `check-avoided-words` and `check-proof-statements` share the engine and set their own defaults.
