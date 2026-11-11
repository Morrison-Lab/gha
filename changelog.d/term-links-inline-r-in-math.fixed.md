- `check-term-links` no longer reads inline math as prose when an inline R expression sits next to a `$` delimiter, as in ``$p = `r 0.5`$``.
  The code span used to be blanked with spaces first, which left a space at the `$` and stopped the math from matching (#1143).
