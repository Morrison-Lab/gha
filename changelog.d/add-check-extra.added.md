- **New `check-extra` capability** (composite action + `check-extra.yml`
  reusable workflow) (#335).
  Three R-package checks that `R CMD check` passes over, adapted from
  [`IndrajeetPatil/workflows`](https://github.com/IndrajeetPatil/workflows)
  `check-extra.yaml` (MIT).
  Warnings as errors (`options(warn = 2L)`) on examples, tests, and
  vignette `.Rmd` files -- with the testthat#1912 workaround of calling
  `testthat::test_file()` per script inside `withr::local_options`, because
  parallel testthat does not honor a global `warn` option.
  Random test order via `testthat::test_dir("tests/testthat", shuffle = TRUE)`
  with a logged seed and `TESTTHAT_PARALLEL=FALSE`.
  README.Rmd render with warnings as errors, plus a freshness gate that
  fails when `README.md` is modified or untracked after the knit, so this
  can replace a bespoke `check-readme.yaml` rather than duplicate it.
  Each check is its own job so every failure surfaces at once.
  `purrr`, `withr`, `fs`, `cli`, and `pkgload` are declared in
  `extra-packages` rather than arriving transitively via `devtools`.
  Independent checks are inputs (`check-warnings`, `check-random-order`,
  `check-readme`) rather than a monolith.
  Ships at `@v2` (too new to exist at the frozen `@v1` tag).
