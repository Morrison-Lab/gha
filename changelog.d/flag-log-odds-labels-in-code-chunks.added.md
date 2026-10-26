- **`check-literal-math-letters` flags a bare `z` or `F` for the log-odds in the label strings of a code chunk** (lds#1411).
  It reads the strings inside `labs()`, `xlab()`, `ylab()`, `ggtitle()`, `expression()`, `scale_*()`, `legend()`, `set_xlabel()`, `set_ylabel()` and `set_title()`,
  and the value of a `label`, `subtitle`, `caption`, `title`, `xlab`, `ylab`, `main` or `sub` argument, including inside `paste0()`, across lines and in triple-quoted strings.
  A call that spans several lines is followed until its parentheses close.
  A string must name the log-odds or logit to be flagged, so `Score z` passes.
  An argument such as `label` or `title` counts only in a plot call (`plot()`, `legend()`, `layout()`, `geom_*()`, `scale_*()` and similar), so `data.frame(label = ...)` and `theme(plot.title = ...)` are skipped, and the argument ends at the first value that is not a string or a call.
  Comments and `{...}` fields in a string are skipped.
  Known limits: a label split across lines inside one ordinary string, a `\n` escape right before the symbol, `ax.set(xlabel = ...)`, and a symbol in a separate string joined by `paste0()` are not read.
  A bare symbol in `expression(paste("Log-odds ", z))` is not read, only strings.
  A comment `check-literal-math-letters: allow` after a `#` on a line of the chunk exempts that line and the next;
  the same words inside a string exempt nothing.
