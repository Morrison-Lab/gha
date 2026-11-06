- **`preview` and `quarto-publish` use reticulate's managed Python environment**
  ([#1540](https://github.com/Morrison-Lab/gha/issues/1540)).
  Both composites now export `RETICULATE_USE_MANAGED_VENV=yes` before rendering.
  A persistent virtualenv on a self-hosted runner can no longer shadow the uv
  environment that `reticulate::py_require()` builds.
  That shadowing made pages that require a new package fail with
  `ModuleNotFoundError`.
