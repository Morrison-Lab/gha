- **Add bundled repo actions and reusable workflows**
  (#865).
  Adds six composite actions and paired reusable workflows
  that bundle standard check suites by repository type:
  `check-repo-hygiene` for common repository hygiene and secret leakage checks,
  `check-quarto-website` for Quarto website projects,
  `check-quarto-book` for Quarto book projects,
  `check-quarto-manuscript` for Quarto manuscript and article projects,
  `check-r-package` for R package repositories,
  and `check-python-package` for Python package repositories.
  Provides complete callers in `examples/`,
  reference documentation in `website/reference/`,
  and offline verification tests in `.github/workflows/scripts/tests/run-bundle-repo-actions-tests.py`.
