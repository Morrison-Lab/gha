- `check-one-div-per-subfile`:
  add a diff-scoped, warn-only composite action and reusable workflow that flags a
  Quarto subfile (a `_*.qmd` file under a `_subfiles` directory) holding more than one
  top-level fenced div when a pull request adds a line to it
  ([#1092](https://github.com/Morrison-Lab/gha/issues/1092)).
  New and revised content gets one div per subfile, a solution in its own `_sol` file included.
  A touched subfile with an unclosed div, code fence or HTML comment is reported too
  (an error under `fail`), and a notice counts glob matches that are not subfiles.
  Nested divs, `rem-source-` remarks, blockquoted divs, HTML comments and fenced code do not count,
  and an untouched subfile keeps its layout, so existing files are never reflagged.
  Like `check-literal-math-letters` it scopes to added lines (a moved line is not new),
  skips rather than scanning the whole tree when there is no base to diff against,
  and has a `whole-tree` mode that measures how many existing subfiles hold several divs.
