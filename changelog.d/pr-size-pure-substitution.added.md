- `check-pr-size`:
  exempt a diff that is a pure rename,
  so a mechanical rename across many files passes without the label or the "mechanical, content-identical" phrase (#2050).
  Every hunk must add as many lines as it removes.
  Every changed line must differ only by one consistent map of at most 10 renames.
  A rename swaps one macro or identifier for another.
  Punctuation, numbers, and logic words such as `true` never count as renames.
  The check prints the map it found.
