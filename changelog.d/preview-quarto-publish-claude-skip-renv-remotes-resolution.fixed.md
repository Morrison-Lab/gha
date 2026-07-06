- **`preview`, `quarto-publish`, and `claude`'s renv-restore steps no longer
  re-resolve a consumer's `DESCRIPTION` `Remotes:` field against the GitHub
  API on every run** (#239). `renv::restore()` doesn't need that field at
  all -- every package's remote metadata (`RemoteType`/`RemoteHost`/
  `RemoteRepo`/`RemoteSha`) is already recorded directly in `renv.lock`. The
  extra consistency check this field triggers (gated by renv's
  `install.remotes` config option, on by default) was a flaky, rate-limited
  network dependency with no effect on which package versions actually get
  restored -- see `d-morrison/rme#994` for a reproduction. `RENV_CONFIG_INSTALL_REMOTES: false`
  is now set alongside each `r-lib/actions/setup-renv` call in these three
  actions.
