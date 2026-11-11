- `check-static-figures`:
  add a diff-scoped, warn-only composite action plus a reusable workflow that flags
  an interactive figure that runs only in HTML output with no static version in its file,
  and a note sending readers to the HTML version instead of showing the figure
  ([#1822](https://github.com/Morrison-Lab/gha/issues/1822)).
  A file holding `<!-- static-version: reason -->` is exempt.
  Like `check-exm-figures` it scopes to added lines, skips rather than scanning
  the whole tree when there is no base to diff against, and has a `whole-tree` mode.
  Set `fail: true` to block.
