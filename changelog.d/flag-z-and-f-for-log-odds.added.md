- **`check-literal-math-letters` flags a bare `z` or `F` standing for the log-odds** (lds#1411).
  It fires on a line that names the log-odds or logit and has a standalone `z` or `F` in its math, in both modes,
  with `\logodds` as the suggested macro.
  It skips subscripts, superscripts, applied functions such as `F(x)`, text arguments,
  the `\logodds` macro itself, and lines about a Wald statistic, a quantile or a test.
