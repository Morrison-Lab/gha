- `check-term-links`:
  treat an added line as moved when an unchanged line of another file in the same directory holds the same text,
  ignoring indentation and a list marker,
  so a split that keeps the original file no longer flags every line of its parts
  ([gha#1792](https://github.com/Morrison-Lab/gha/issues/1792)).
  Measured on mlg#319: 66 findings with the original kept before this change.
