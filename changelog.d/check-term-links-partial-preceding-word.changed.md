- **`partial-link` in `check-term-links` now also fires on the word before a link**:
  `10-fold [cross-validation](...#def-cross-validation)` is flagged
  when the target is titled `$k$-fold cross-validation`,
  and so are `ten-fold` and `$K$-fold`.
  An `unlinked-first-use` finding preceded by such a word names the whole phrase
  ("'5-fold cross-validation' is a defined term").
  Measured 2026-11-26 over lds (whole tree): 15 new findings, all real.
  A function word after a link no longer counts as a missing title word,
  so `[lasso](...#def-lasso) and ridge` passes;
  that drops four false findings in lds and no true one.
