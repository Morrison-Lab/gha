- `check-informal-definitions` reports fewer false positives (gha#1482).
  It tracks a bare-class div such as `::: proof`,
  and skips proof and solution divs.
  It also passes local abbreviations such as `Let $S_n \eqdef ...$`,
  leading bold labels, notation sentences,
  unnamed "X is:" lines before display math,
  and variants of a counted term in one definition div.
  Across the lds, mds, pds, sds, and psw notes, findings fell from 477 to 367.
