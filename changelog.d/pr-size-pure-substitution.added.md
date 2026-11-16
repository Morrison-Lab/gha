- `check-pr-size`:
  exempt a diff that is a pure token substitution
  (every hunk adds as many lines as it removes, and every changed line differs only by one consistent map of at most 10 single-word replacements),
  so a mechanical rename across many files passes without the label or the "mechanical, content-identical" phrase (#2050).
  The check prints the map it found.
