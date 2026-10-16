- **`R_GITHUB_PAT` secret on `preview.yml` and `quarto-publish.yml`**,
  passed to the R dependency step as `GITHUB_PAT` when set.
  The default `github.token` sees only the caller repository, so a site whose
  `r-packages` or `Remotes:` names a private package (`Morrison-Lab/qnp` in
  `Morrison-Lab/pds`) failed with "Can't find GitHub repo".
  Unset keeps the current behavior, so existing callers are unaffected.
