- `check-exercise-before-result`:
  add a diff-scoped, blocking composite action and reusable workflow that flags a `#thm-`, `#lem-`, `#cor-` or `#prp-` div
  added or edited without an exercise and its solution just before it, read from the chapter's include order
  ([#1242](https://github.com/Morrison-Lab/gha/issues/1242)).
  A heading, example or other block between the solution and the result breaks adjacency.
  `<!-- check-exercise-before-result: allow -->` on the first line of a result exempts it.
