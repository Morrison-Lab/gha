- `lint-changed-lines` no longer runs `setup-r-dependencies` when `install-package` is `false`.
  A repository whose `DESCRIPTION` is only a dependency manifest, and a private runner without passwordless `sudo`, then get `gh`, `lintr` and any `extra-packages` from CRAN like a repository with no `DESCRIPTION`.
