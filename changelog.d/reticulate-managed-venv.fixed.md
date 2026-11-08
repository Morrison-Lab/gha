- **`preview` and `quarto-publish` set `RETICULATE_USE_MANAGED_VENV=yes` before the render**
  ([#1540](https://github.com/Morrison-Lab/gha/issues/1540)).
  A persistent virtualenv on a self-hosted runner no longer shadows the environment
  `reticulate::py_require()` builds.
  A value the caller already set is kept.
