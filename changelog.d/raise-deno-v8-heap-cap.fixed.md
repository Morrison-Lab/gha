- **`preview` and `quarto-publish` no longer crash on large Quarto sites**
  ([#262](https://github.com/d-morrison/gha/issues/262)). Both composites now
  raise Quarto's Deno V8 heap cap from the launcher default of 8 GB to 12 GB
  (via `QUARTO_DENO_V8_OPTIONS`) before rendering, so large multi-chapter
  sites no longer crash late in `quarto render` with `Fatal JavaScript out of
  memory` / exit code 133.
