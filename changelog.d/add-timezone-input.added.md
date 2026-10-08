- **`timezone` input on `preview` and `quarto-publish`** (composites and
  reusable workflows), defaulting to `''` so existing callers are unaffected.
  A non-empty value is exported as `TZ` before the render, so
  `date: last-modified` stamps read in that zone instead of UTC.
  A value containing a newline or `=` fails the step, since it is written to
  `GITHUB_ENV`
  ([gha#1025](https://github.com/Morrison-Lab/gha/issues/1025), item 1).
