- `lint-changed-lines` no longer activates a repository's `renv` project when `use-renv` is `false`.
  The steps that install `lms` and lint set `RENV_CONFIG_AUTOLOADER_ENABLED` to `false`, so a repository with an `renv` autoloader in `.Rprofile` can use `lms-ref` without its install failing on the `renv` cache directory.
