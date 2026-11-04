- `check-proof-statements`:
  fail by default instead of warning (Ezra, 2026-11-04; gha#1471).
  A whole-tree run over lds, mds, pds, sds and psw was sampled and every reasoning-word hit in a theorem statement was a real violation.
  The `fail` input default changes from `false` to `true`, in the action and the reusable workflow.
  A proof hidden from the slides is a deliberate choice, so the check no longer flags one (Ezra, 2026-11-04; gha#1491).
  Reasoning words fail only on added lines.
  A caller that wants warnings sets `fail: false`.
