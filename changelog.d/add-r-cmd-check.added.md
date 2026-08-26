- **New `r-cmd-check` reusable workflow** (#331).
  Runs `R CMD check` across an OS × R-version matrix
  (r-lib's 5-way default), wrapping
  [`r-lib/actions`](https://github.com/r-lib/actions).
  A second caller job with `hard: true` runs a
  Depends/Imports/LinkingTo-only check on `pull_request`,
  with `cache: false` so a restored pak cache cannot silently
  contain Suggests -- two designs from
  [`IndrajeetPatil/workflows`](https://github.com/IndrajeetPatil/workflows)
  (MIT), not a verbatim port of `rpt`'s bespoke
  `R-CMD-check.yaml`.
  `error-on` defaults to `'"note"'` to match rpt, and
  `_R_CHECK_CRAN_INCOMING_REMOTE_`,
  `_R_CHECK_FORCE_SUGGESTS_`, and
  `_R_CHECK_STOP_ON_INVALID_NUMERIC_VERSION_INPUTS_`
  are inputs rather than hard-coded.
  Julia, Quarto, pandoc, recursive submodules, and a Linux
  container (`rocker/verse:latest` on rpt) are inputs so a
  consumer can match a bespoke workflow step-for-step;
  the hard job never uses `linux-container`, because a verse
  image already contains Suggested packages.
  This PR does not migrate `rpt`.
  Pin to `@v2` after the major tag slides past this merge.
