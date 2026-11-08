- `preview.yml` and `quarto-publish.yml`: `cluster-render: true` now also skips the runner-side toolchain steps, as `preinstalled-toolchain: true` does.
  A no-sudo lab runner no longer fails at `Install Quarto` before the cluster step (gha#1642).
