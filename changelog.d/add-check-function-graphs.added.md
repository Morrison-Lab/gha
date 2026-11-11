- `check-function-graphs`:
  add a diff-scoped, warn-only composite action plus a reusable workflow that flags
  a definition div (`#def-`) of a function of one or two inputs with no graph inside it
  ([#1838](https://github.com/Morrison-Lab/gha/issues/1838)).
  A div holding `<!-- no-graph: reason -->` is exempt.
  Like `check-exm-figures` it scopes to added lines, skips rather than scanning
  the whole tree when there is no base to diff against, and has a `whole-tree` mode.
  Set `fail: true` to block.
