- `check-solution-citations`:
  add a diff-scoped, blocking composite action and reusable workflow that flags a citation of a solution (`@sol-`)
  inside a `proof` div or a `#thm-`, `#lem-`, `#cor-` or `#prp-` div
  ([#1234](https://github.com/Morrison-Lab/gha/issues/1234)).
  A derivation cites a result div that follows the solution, not the solution itself.
  The exception is an exercise that asks students to prove the result before it is stated:
  `<!-- check-solution-citations: allow -->` on the line, or a sentence reading "the solution (or answer) to @exr-slug", exempts `@sol-slug`.
  Like `check-def-commentary` it scopes to added lines and skips rather than scanning the whole tree without a base.
  Code fences, display math, HTML comments and inline code are not read.
