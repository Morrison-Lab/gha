- `check-literal-math-letters`: add a `letters` input that restricts the check
  to the named letters or Greek commands, so a caller can block one letter whose
  macro is certain without the noise of every other letter.
  `J` now suggests `\objfn` (or `\objfnf{...}`), and `known` mode flags it.
  Morrison-Lab/lds wrote the same objective as a hand-typed `J` on one page and
  as `\objfn` on another, and the two printed different glyphs.
  Defaults are unchanged.
