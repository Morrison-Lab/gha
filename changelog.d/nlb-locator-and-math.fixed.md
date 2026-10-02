- `check-new-line-breaks` no longer reads a citation page locator such as
  `[@key, p. 331]` as a sentence boundary;
  `p.` is protected when a digit follows it (#998).
- `check-new-line-breaks` strips inline TeX math (`$...$`) before the
  clause test and skips multi-line `$$ ... $$` display blocks,
  so a semicolon inside a formula is not read as a clause break;
  as in Pandoc, a `$` followed by a digit does not close math,
  so `$5-$10` stays prose (#998).
