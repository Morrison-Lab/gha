- `check-exm-figures`:
  add a diff-scoped, warn-only composite action and reusable workflow that flags an
  example div (`#exm-`) with no figure when a pull request adds a line to it
  ([#1193](https://github.com/Morrison-Lab/gha/issues/1193)).
  A figure is an image, a `fig-` labelled chunk or div, an `@fig-` reference
  or an include of a `_fig` subfile.
  An `<!-- no-figure: reason -->` comment inside the div is the justified exception,
  and `paths-ignore` exempts whole paths.
  Like `check-one-div-per-subfile` it scopes to added lines, skips rather than scanning
  the whole tree when there is no base to diff against, and has a `whole-tree` mode.
