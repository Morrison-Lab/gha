- **`ghatools` and workflow integration:**
  Consolidated standalone diff and version helpers onto the `ghatools` package,
  safeguarded fallback package resolution paths against out-of-bounds indexing,
  required `testthat` in the `ghatools` selftest runner,
  and fixed `check-bibliography-dois` R-dependency installation via `packages` (#498).
