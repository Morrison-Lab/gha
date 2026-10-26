- `check-tree-lists`:
  add a diff-scoped, blocking composite action and reusable workflow that flags a
  definition, example, theorem-type, remark or exercise div that mentions a tree,
  holds a list nested three or more levels deep and has no figure, when a pull
  request adds a line to it
  ([#1263](https://github.com/Morrison-Lab/gha/issues/1263)).
  A tree is drawn as a diagram figure, not only written as nested bullets.
  An `<!-- no-tree-figure: reason -->` comment inside the div is the justified
  exception, and `paths-ignore` exempts whole paths.
  Like `check-exm-figures` it scopes to added lines, skips rather than scanning
  the whole tree when there is no base to diff against, and has a `whole-tree` mode.
