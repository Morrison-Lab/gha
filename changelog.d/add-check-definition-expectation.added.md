- `check-definition-expectation`:
  add a diff-scoped, warn-only heuristic composite action with a reusable workflow
  that flags a definition div (`#def-`) that a PR edits
  and that writes a probability-weighted sum or integral with no expectation operator
  ([gha#1573](https://github.com/Morrison-Lab/gha/issues/1573); Ezra, 2026-11-07; psw#513).
  It skips sample averages, a lone density, and a div titled "Expectation".
  `<!-- check-definition-expectation: allow -->` exempts a definition.
  Warns by default.
