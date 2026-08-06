- **`quarto-publish`'s TinyTeX install no longer 403s on shared runners**
  (#270).
  The "Set up Quarto" step now passes `GH_TOKEN: ${{ github.token }}`,
  so `quarto install tinytex`'s latest-release lookup against
  `rstudio/tinytex-releases` is authenticated rather than an unauthenticated
  GitHub API call that intermittently fails with `403 - Forbidden`
  (`Unable to determine latest release for rstudio/tinytex-releases`).
  Only affects callers with `tinytex: true`; matches the `preview` composite,
  which already authenticates the same step.
