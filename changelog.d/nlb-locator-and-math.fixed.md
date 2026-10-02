- `check-new-line-breaks` no longer reads a citation page locator such as
  `[@key, p. 331]` as a sentence boundary;
  `p.` is protected when a digit follows it (#998).
- `check-new-line-breaks` strips inline TeX math (`$...$`) before the
  clause test and skips multi-line `$$ ... $$` display blocks
  and raw TeX math environments such as `\begin{align}`
  (each up to its `\end{...}` or a blank line,
  even when the opener ends a line of prose,
  though not when it is named mid-sentence or in a code span),
  so a semicolon inside a formula is not read as a clause break;
  as in Pandoc, a `$` followed by a digit does not close math,
  so `$5-$10` stays prose (#998).
