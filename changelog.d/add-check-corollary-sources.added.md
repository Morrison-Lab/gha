- `check-corollary-sources`:
  add a diff-scoped, warn-only composite action with a reusable workflow
  that flags a corollary div (`#cor-`) that a PR edits
  and whose statement and proof name no earlier result
  (an `@thm-`, `@lem-`, `@cor-` or `@prp-` cross-reference, or a link to such an anchor)
  (Ezra, 2026-11-16; Morrison-Lab/psw#668).
  `<!-- check-corollary-sources: allow: reason -->` exempts a corollary.
  Warns by default.
