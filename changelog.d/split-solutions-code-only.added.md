- `check-split-solutions`:
  warn when a solution's code reports a statistic that only a sibling exercise asks for,
  the code-only splits that the figure rule cannot see
  (found by hand in lds#1538, lds#1539 and lds#1540).
  The finding is a heuristic, so it is always a warning and never fails the run, even with `fail: true`.
  It reads a short list of terms (correlation, R-squared, residual, variance inflation, F-test,
  p-value, standard error, indicator columns) and ignores assignments, definitions, imports,
  hidden chunks and comments inside a function.
