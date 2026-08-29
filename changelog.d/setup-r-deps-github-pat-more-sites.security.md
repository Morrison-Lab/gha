- **`quarto-publish`, `test-coverage`, `check-extra`, `preview`,
  `check-bibliography-dois`, and `spellcheck` now export `GITHUB_PAT` on
  their `setup-r-dependencies` steps, and so do `claude.yml`'s and
  `gemini.yml`'s own DESCRIPTION-based "Install R dependencies" steps**
  (#737).
  Each already sets `GITHUB_PAT` on its renv path where one exists (the
  `RENV_CONFIG_INSTALL_REMOTES: false` steps), but the
  DESCRIPTION/`packages:`-based dependency install lacked it, so a consumer
  whose `DESCRIPTION` carries GitHub `Remotes:` entries resolved them via
  unauthenticated GitHub API calls from shared runner IPs -- the same
  rate-limit flake risk #734/#738 fixed for `lint-changed-files` and
  `lint-changed-lines`.
  `claude.yml` and `gemini.yml` are the two highest-traffic call sites in
  this sweep, since every `@claude`/`@gemini` agent dispatch against an
  R-package consumer runs through them; the review round on this PR caught
  that the original sweep's `--include=action.yml` grep structurally
  excluded them and `spellcheck/action.yml`.
  `_selftest.yml`'s own `ghatools` fixture setup gets the same fix too, for
  consistency, though it carries no consumer-facing risk since it only ever
  reads this repo's own tree.
