- **`check-r-head`**
  ([#2122](https://github.com/Morrison-Lab/gha/issues/2122)):
  add a diff-scoped composite action and reusable workflow
  that fails a pull request that prints a dataset through `head()` in R
  inside a data div,
  such as `head(df)` or `df |> head()`.
  A data div is any R chunk of a `_dat-*` subfile (the `data-files` input)
  or any R chunk inside a fenced div whose id starts `#dat-`.
  The format's `df-print` decides how much of a data frame each reader sees,
  so the chunk prints the data frame itself.
  An assigned or used `head()`, and any `head()` outside a data div, pass.
  Only lines a PR adds count, so existing pages never block.
