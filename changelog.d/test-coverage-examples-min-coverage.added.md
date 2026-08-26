- **`test-coverage` gains examples/vignette coverage and a `min-coverage`
  threshold** (#334). A new `examples-coverage` job (off by default) runs
  `covr::package_coverage(type = c("examples", "vignettes"),
  commentDonttest = FALSE, commentDontrun = FALSE)` so `\donttest{}` and
  `\dontrun{}` blocks actually execute -- the paths `R CMD check` and the
  unit suite skip. A `min-coverage` input (empty default, so current jobs
  stay green) fails the tests job when `covr::percent_coverage()` is below
  the given percent; it does not inherit a 100% bar and does not apply to
  the examples job, which measures a different execution path. Adapted from
  IndrajeetPatil/workflows `test-coverage.yaml` (MIT).
