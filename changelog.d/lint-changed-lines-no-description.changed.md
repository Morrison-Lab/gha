- `lint-changed-lines` no longer needs a `DESCRIPTION` file.
  When `path` holds none, it installs `gh`, `lintr` and any `extra-packages` from CRAN instead of calling `setup-r-dependencies`, so a repository of Quarto pages can lint its R chunks.
