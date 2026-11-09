- `check-result-definition-links`:
  add a diff-scoped, warn-only composite action with a reusable workflow
  that flags a result div (`#thm-`, `#lem-`, `#cor-`, `#prp-`) that a PR edits
  and that links no definition (an `@def-` cross-reference or a link to a `#def-` anchor)
  (Ezra, 2026-11-09).
  `<!-- check-result-definition-links: allow -->` exempts a div.
  Warns by default.
