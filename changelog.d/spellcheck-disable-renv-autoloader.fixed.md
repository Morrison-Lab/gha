- **`spellcheck` now disables the renv autoloader during dependency setup**
  ([#620](https://github.com/Morrison-Lab/gha/issues/620)).
  Previously, `setup-r-dependencies` detected a repository's `renv.lock` and
  `.Rprofile` and installed `{spelling}` into the project's renv library.
  Because the upstream action runs `Rscript` with `--vanilla` by default,
  `.Rprofile` was never sourced and R failed to locate `{spelling}`.
  Setting `RENV_CONFIG_AUTOLOADER_ENABLED: 'FALSE'` ensures `{spelling}` installs
  into the site library where `--vanilla` finds it.
