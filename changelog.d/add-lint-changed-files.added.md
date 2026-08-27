- **New `lint-changed-files` capability** (composite action +
  `lint-changed-files.yml` reusable workflow) (#258).
  Runs [`lintr`](https://lintr.r-lib.org/) at one of three scopes selected by
  a `scope` input: the files a pull request changed (default; the r-lib
  example pattern `ucdavis/win`, `Morrison-Lab/rpt`, and `d-morrison/qwt`
  each carry as a bespoke copy), a whole package (`lintr::lint_package()`),
  or a whole project (`lintr::lint_dir()`).
  lintr is installed from CRAN, never from `r-lib/lintr` on GitHub HEAD.
  `lint-changed-lines` stays a separate capability -- its added-lines
  diffing is different machinery from these three whole-file scopes, and
  folding it in would have rewritten a released composite onto a nested
  `@v2` action that does not resolve until the tag slides.
