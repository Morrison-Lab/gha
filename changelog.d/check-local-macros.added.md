- `check-local-macros`:
  add a diff-scoped, warn-only composite action and reusable workflow that flags
  LaTeX macros defined outside `Morrison-Lab/macros` (`\newcommand`, `\def`,
  `\DeclareMathOperator` and the rest) on lines a pull request adds.
  A `macros-override.*` file may redefine only a macro the library already has,
  checked against the files named in `library`.
  This is check 2 of
  [#1077](https://github.com/Morrison-Lab/gha/issues/1077);
  check 1 is `check-literal-math-letters`.
