- `check-definition-equations`:
  fail by default instead of warning (gha#1479).
  Equations separated by `\quad` or `\qquad` are read one at a time,
  so a display with two equations or an index range is no longer a chain.
  A whole-tree run over lds, mds, pds, sds, and psw was sampled,
  and every remaining hit was a real violation.
  The `fail` input default changes from `false` to `true`, in the action and the reusable workflow.
  A caller that wants warnings sets `fail: false`.
