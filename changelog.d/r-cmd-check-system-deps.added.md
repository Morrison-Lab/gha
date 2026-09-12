- **`r-cmd-check` adds system dependency and Julia project inputs**:
  Added `apt-packages` (defaulting to the standard R system libraries list
  on Linux cells without a container, and on the hard job),
  `julia-project` (default `'inst/julia'`), `brew-packages` (with automatic
  force-linking and `~/.R/Makevars` config when `gettext` is included), and
  `brew-casks` inputs, as well as `PKG_INCLUDE_LINKINGTO: "true"` in both
  jobs' environment.
  This allows `ucdavis/bcs` to migrate from its bespoke `R-CMD-check.yaml`
  to reusable `r-cmd-check.yml@v2` (closes #824).
