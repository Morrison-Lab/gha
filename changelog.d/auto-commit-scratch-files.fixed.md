- **`claude.yml` and `gemini.yml` no longer auto-commit session scratch files or setup artifacts** (#981, #983).
  The residual auto-commit sweep pushed `.tmp_*` scratch scripts and untracked setup artifacts
  (such as `setup-r-dependencies`' `.github/pkg.lock` and `.github/r-depends.rds`)
  onto PR and issue branches when uncommitted changes were swept.
  The workflows now purge untracked `.tmp_*` files and setup artifacts
  (restoring tracked versions to HEAD if present) prior to the auto-commit step,
  and the agent prompt advises writing scratch scripts outside the checkout in `$RUNNER_TEMP`.
