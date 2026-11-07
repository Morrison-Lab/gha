- `check-results-in-remarks`:
  add a diff-scoped, warn-only heuristic composite action with a reusable workflow
  that flags a remark div (`#rem-`) that a PR edits
  and that displays an equation and states a claim
  ([gha#1571](https://github.com/Morrison-Lab/gha/issues/1571); Ezra, 2026-11-07; psw#512).
  A result belongs in a theorem-type div with its proof,
  and the remark keeps the commentary.
  `<!-- check-results-in-remarks: allow -->` exempts a remark.
  Warns by default.
