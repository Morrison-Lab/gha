- **`check-python-qmd-chunks` action and reusable workflow.**
  Lints the Python chunks of the `.qmd` files a pull request changes with the
  repository's `ruff.toml`, joining a file's chunks in document order and
  reporting each finding at its `.qmd` line.
  Fails by default.
  The lab configuration is `python/ruff.toml` in
  [`Morrison-Lab/psc`](https://github.com/Morrison-Lab/psc)
  ([gha#1468](https://github.com/Morrison-Lab/gha/issues/1468)).
