- **Example stubs and reference docs for 7 more capabilities pinned the frozen
  `@v1` tag while `main` had picked up real fixes since the freeze** (#182).
  `examples/check-bibliography-dois.yml`, `check-phi.yml`, `check-links.yml`,
  `check-non-standard-chars.yml`, `claude.yml`, and `claude-code-review.yml`,
  plus their matching `website/reference/*.qmd` pages, and
  `examples/update-snapshots.yml` (which has no reference page), all pinned
  `@v1`. A consumer following those stubs would miss: the
  `ANTHROPIC_API_KEY` secret (direct API / GitHub App auth, an alternative to
  `CLAUDE_CODE_OAUTH_TOKEN`) on `claude.yml` and `claude-code-review.yml`; a
  security fix on `claude-code-review.yml` for unauthorized commits from tag
  mode, plus its `track-progress`, `apt-packages`, and `pip-packages` inputs;
  and dependency-pin bumps (`actions/setup-python`, `r-lib/actions`,
  `julia-actions/cache`) on `check-bibliography-dois.yml`,
  `check-phi.yml`, `check-non-standard-chars.yml`, and `update-snapshots.yml`.
  `check-links.yml`'s bundled `lychee.default.toml` also gained a
  `claude.ai` exclude, since lychee was reporting its bot-protected 403s as
  dead links. Bumped every stale pin to `@v2`, added the missing
  `ANTHROPIC_API_KEY` secret docs to `claude.qmd`/`claude-code-review.qmd` (and
  to the `README.md`/`website/permissions.qmd` permissions summaries), and
  reworded the `README.md` / `website/workflows.qmd` / `website/versioning.qmd`
  / `CLAUDE.md` versioning prose to describe the per-capability `@v1`/`@v2`
  split instead of a blanket `@v1` default.
  `summary.yml`, `bump-submodule.yml`, and `sync-shared-fragments.yml` were
  audited in the same pass and found unchanged since the freeze, so their
  `@v1` pin stays correct.
