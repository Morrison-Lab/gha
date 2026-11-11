- `check-proof-statements`:
  fail by default instead of warning (Ezra, 2026-11-04; gha#1471).
  A whole-tree run over lds, mds, pds, sds, and psw was sampled,
  and every reasoning-word hit in a theorem statement was a real violation.
  The `fail` input default changes from `false` to `true`, in the action and the reusable workflow.
  Reasoning words fail only on added lines,
  but a proof hidden from the slides fails whenever a PR touches its file.
  gha#1491 dropped the hidden-proof rule on a paraphrase that Ezra did not confirm (2026-11-11).
  psw's rule is to show every proof on the slides, so the rule is back.
  A caller that wants warnings sets `fail: false`.
