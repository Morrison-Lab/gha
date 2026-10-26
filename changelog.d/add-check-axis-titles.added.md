- `check-axis-titles`:
  add a diff-scoped, blocking composite action and reusable workflow that flags an
  axis title with no plain word, such as `"x"`, `"x1"` or `"f(x)"`, when a pull request adds it
  ([#1235](https://github.com/Morrison-Lab/gha/issues/1235)).
  It reads ggplot2 `labs()` (also across lines), `xlab()` and `ylab()`, matplotlib `set_xlabel()`
  and `set_ylabel()`, plotly axis titles, and `expression(...)`/`bquote(...)` titles (only their quoted strings count as words).
  The lab's rule is to name the quantity in plain words with the symbol optional,
  such as "Probability, p" and "Log-odds, η".
  `axis-title-ok: reason` on the line is the justified exception, and `paths-ignore` exempts whole paths.
  Like `check-exm-figures` it scopes to added lines, skips rather than scanning the whole tree
  when there is no base to diff against, and has a `whole-tree` mode.
