- `check-contour-3d`:
  add a diff-scoped, warn-only composite action plus a reusable workflow that flags a
  contour or level-curve plot with no 3D surface plot of the same function
  when a pull request adds a line to its code chunk
  ([#1443](https://github.com/Morrison-Lab/gha/issues/1443)).
  A file passes when it holds a 3D call (`add_surface`, `plot_surface`, `persp`),
  includes a `-3d.qmd` subfile, sits beside a `<name>-3d.qmd` sibling,
  or holds an `<!-- no-3d: reason -->` comment.
  Like `check-exm-figures` it scopes to added lines, skips rather than scanning
  the whole tree when there is no base to diff against, and has a `whole-tree` mode.
  Set `fail: true` to block.
