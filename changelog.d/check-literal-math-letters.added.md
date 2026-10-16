- `check-literal-math-letters`:
  add a diff-scoped, warn-only composite action and reusable workflow that flags
  literal Latin and Greek letters in math in `.qmd`, `.md` and `.Rmd` files,
  where a semantic macro from `Morrison-Lab/macros` belongs (`\outvar` for `y`,
  `\predvar` for `x`, `\param` for `\theta`).
  It skips code, comments, `\text{}`-like commands and `.notation` divs,
  reports how many lines it examined, and skips rather than scanning the whole
  tree when there is no base to diff against.
  This is check 1 of
  [#1077](https://github.com/Morrison-Lab/gha/issues/1077);
  check 2, macros defined outside the macros repository, is a separate change.
