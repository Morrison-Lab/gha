- **`check-literal-math-letters` flags a bare `z` or `F` for the log-odds in the label strings of a code chunk** (lds#1411).
  It reads `labs()`, `xlab()`, `ylab()`, `ggtitle()`, `expression()`, `scale_*()`, `set_xlabel()`, `set_ylabel()`, `set_title()`, `label=`, `name=` and `title=` on a line inside a fence.
  A string must name the log-odds or logit to be flagged, so `Score z` and Wald statistics pass.
  A comment line `check-literal-math-letters: allow` inside the chunk exempts the next line.
