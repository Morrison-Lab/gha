- **`partial-globs` input on `check-quarto-links`.**
  Files matching these globs are treated like `_`-prefixed files:
  a link in one resolves from the page that includes it,
  not from the file's own directory.
  A project whose `render:` list leaves a directory such as `chapters/*/` unrendered
  otherwise gets a false finding for every cross-chapter link in its include-only files
  ([gha#1689](https://github.com/Morrison-Lab/gha/issues/1689)).
