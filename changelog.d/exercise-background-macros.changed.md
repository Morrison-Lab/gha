- `check-exercise-background` reads math macros more closely (gha#1481, gha#1915).
  - It counts a longer macro name only when it adds "s", "es", "fn" or "f" to a word of five letters or more
    (`\gradients`, `\logisticfn`), so `\rightarrow` does not say right.
  - It counts a macro name of five letters or more as saying a longer word it starts (`\noise` says noiseless),
    unless the name is in `SYMBOL_MACROS` or `MACRO_WORDS`, so `\alpha` does not say alphabet.
  - It matches the words a listed macro says only whole, so `\Var` does not say variable.
  - It treats grouping, size, spacing and colour macros (`\paren`, `\large`, `\color`) as saying nothing.
