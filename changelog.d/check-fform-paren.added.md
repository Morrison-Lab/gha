- **`check-fform-paren`**
  ([#1082](https://github.com/Morrison-Lab/gha/issues/1082)):
  add a diff-scoped, warn-only composite action and reusable workflow that flags
  `\name\paren{...}` (or `\name\sb{...}`, `\name\cb{...}`) on lines a pull request adds when a `\namef{...}` macro exists,
  and suggests `\namef{...}`.
  The known f forms are read from the `\providecommand{\XXXf}` and `\newcommand{\XXXf}`
  definitions in `macros-file` (default `latex-macros/macros.qmd`);
  a missing file skips the check with a warning.
  A bare `\paren{`, `\sb{` or `\cb{` and a macro with no f form pass.
  Companion to
  [ai-config#4597](https://github.com/Morrison-Lab/ai-config/issues/4597).
