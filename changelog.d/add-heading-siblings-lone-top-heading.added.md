- `check-heading-siblings`:
  also flag a page whose top level holds a single heading when a pull request adds that heading
  (new `min` input, default 2; `0` turns it off).
  A lone top-level heading gives the table of contents one entry that usually restates the page title,
  as on lds `discriminant-analysis.qmd`.
  Diff-scoped like the upper bound, so existing pages are not swept.
