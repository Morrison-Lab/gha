- `preview` and `quarto-publish` pass `no-sudo` to `browser-actions/setup-chrome` on a runner without passwordless sudo.
  Chrome then installs without `sudo` instead of failing the step (gha#1642).
