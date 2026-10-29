- `lint-changed-lines` also turns off the `renv` autoloader in its `setup-r-dependencies` step, and in the `R CMD INSTALL` step unless `use-renv` is `true`, so `gh` and `lintr` are installed where the lint step looks for them.
  The install step for a repository with no `DESCRIPTION` now sets a CRAN mirror when the runner has none.
