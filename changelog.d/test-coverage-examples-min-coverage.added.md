- **`test-coverage` gains examples/vignette coverage and a `min-coverage`
  threshold** ([#334](https://github.com/Morrison-Lab/gha/issues/334)).
  A new `examples-coverage` job (off by default) runs
  `covr::package_coverage(type = c("examples", "vignettes"),
  commentDonttest = FALSE, commentDontrun = FALSE)`.
  `\dontrun{}` does not run under `R CMD check` by default
  (only with `--run-dontrun`, which `--as-cran` does not imply).
  `\donttest{}` is skipped unless `--as-cran` or `--run-donttest`
  (r-lib's `check-r-package` defaults `--as-cran`, which *does* run them).
  covr comments both out by default.
  The examples job passes the flags false so those blocks execute for coverage.
  A `min-coverage` input defaults to no threshold
  (empty, so current jobs stay green)
  and fails the tests job when `covr::percent_coverage()` is below
  the given percent;
  it does not apply to the examples job,
  which measures a different execution path.
  Checkout now sets `persist-credentials: false`.
  New reusable-workflow `with:` keys are inert until `@v2` slides
  past this change.
  Adapted from IndrajeetPatil/workflows `test-coverage.yaml` (MIT).
