- **The `preview`, `quarto-publish`, `lint-changed-lines` and `lint-changed-files` actions**
  install Quarto through `install-quarto`, which serves the pinned 1.11.9 release from the
  release cache and falls back to the setup action, so a release-host outage no longer blocks them (gha#1678).
  They now install the pinned 1.11.9 rather than the latest release.
  `student-qmd` follows after the next `v3` slide, because its `quarto-version` input needs the version pass-through added here.
