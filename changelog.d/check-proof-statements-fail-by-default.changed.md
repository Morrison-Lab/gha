- `check-proof-statements`:
  fail by default instead of warning (Ezra, 2026-11-04; gha#1471).
  A whole-tree run over lds, mds, pds, sds and psw (81 findings) was sampled and every hit was a real violation.
  The `fail` input default changes from `false` to `true`, in the action and the reusable workflow.
  Reasoning words in a theorem statement fail only on added lines, but a proof hidden from the slides fails whenever a PR touches its file.
  A caller that wants warnings sets `fail: false`.
