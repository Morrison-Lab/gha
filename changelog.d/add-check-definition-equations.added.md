- `check-definition-equations`:
  add a diff-scoped, warn-only composite action and reusable workflow
  that flags a definition div (`#def-`) showing more than the equation
  linking the defined symbol to its definitional expression (Ezra, 2026-10-29).
  It flags a display equation that chains equalities after the defining one,
  a definition that displays several equations,
  and prose stating an equivalence ("equivalently", "in other words", "is equivalent to").
  Equalities and equivalences belong in a result after the definition.
  `<!-- def-equiv-ok: reason -->` exempts a definition.
  It warns by default, because the heuristic cannot tell which side of a single
  `a = b` is the defined symbol,
  and checks only definitions that the pull request edits.
