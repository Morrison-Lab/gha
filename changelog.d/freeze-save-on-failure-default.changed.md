- **`freeze-cache-save-on-failure` now defaults to `true` on `quarto-publish`.**
  A publish that fails or is cancelled saves the pages it already executed,
  so the next run resumes instead of starting cold.
  Only sds had set the input; a caller that wants the old behavior passes
  `false` ([gha#1521](https://github.com/Morrison-Lab/gha/issues/1521)).
