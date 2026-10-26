- **`check-literal-math-letters` flags a bare `z` or `F` for the log-odds in the label strings of a code chunk** (lds#1411).
  It reads the strings inside `labs()`, `xlab()`, `ylab()`, `ggtitle()`, `expression()`, `scale_*()`, `legend()`, `set_xlabel()`, `set_ylabel()` and `set_title()`,
  and the value of a `label`, `subtitle`, `caption`, `title`, `xlab`, `ylab`, `main` or `sub` argument, including inside `paste0()`, across lines and in triple-quoted strings.
  A call that spans several lines is followed until its parentheses close.
  A string must name the log-odds or logit to be flagged, so `Score z` passes.
  Comments, f-string fields such as `{z}` and strings outside a label (a `data.frame(name = ...)`) are skipped.
  A bare symbol in `expression(paste("Log-odds ", z))` is not read, only strings.
  A comment `check-literal-math-letters: allow` after a `#` on a line of the chunk exempts that line and the next;
  the same words inside a string exempt nothing.
