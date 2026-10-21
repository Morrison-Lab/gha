- `check-definite-antecedents`:
  add a diff-scoped, warn-only composite action and reusable workflow that flags a
  div (or a file with no div) whose first sentence starts with an unlinked
  "The", "These", "Those", "This" or "That", so nothing earlier in the div can be its antecedent
  ([psw#291](https://github.com/Morrison-Lab/psw/issues/291)).
  It is a heuristic for the clearest case, so it never fails by default.
  It scopes to added lines, skips rather than scanning the whole tree when there is no base,
  and has a `whole-tree` mode.
