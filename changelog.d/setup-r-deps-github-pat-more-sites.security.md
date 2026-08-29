- **`quarto-publish`, `test-coverage`, `check-extra`, `preview`, and
  `check-bibliography-dois` now export `GITHUB_PAT` on their
  `setup-r-dependencies` steps** (#737).
  Each already sets `GITHUB_PAT` on its renv path where one exists (the
  `RENV_CONFIG_INSTALL_REMOTES: false` steps), but the
  DESCRIPTION/`packages:`-based dependency install lacked it, so a consumer
  whose `DESCRIPTION` carries GitHub `Remotes:` entries resolved them via
  unauthenticated GitHub API calls from shared runner IPs -- the same
  rate-limit flake risk #734/#738 fixed for `lint-changed-files` and
  `lint-changed-lines`.
