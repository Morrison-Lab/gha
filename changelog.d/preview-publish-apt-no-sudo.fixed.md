- `preview` and `quarto-publish` skip the apt step when every package is already installed.
  On a runner without passwordless sudo, they warn and continue instead of failing at `sudo apt-get update`.
  This is the same behavior `lint-changed-files`, `lint-changed-lines`, and `update-snapshots` already have (gha#1642).
