- **`check-fragments` on `check-quarto-links` skips a page with a `results: asis` chunk.**
  Headings that such a chunk writes at render time, like a glossary built from a CSV file,
  exist in no source file, so links to them were reported as dead anchors
  ([gha#1683](https://github.com/Morrison-Lab/gha/issues/1683)).
