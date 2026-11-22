- `check-avoided-words` warns on a line a pull request adds
  that says "intercept" or "intercepts" without saying which concept it means:
  the intercept of a function $f$, the value $f(0)$,
  or the intercept term of an expression, its constant term, such as $\beta_0$ in $\beta_0 + \beta_1 x$
  (Ezra, 2026-11-22; psw word-choice.qmd).
  "intercept term(s)", "intercept(s) of", "y-intercept", "x intercept",
  a link to `#def-intercept` or `#def-intercept-term`, hyphenated compounds and ids pass,
  as do code, math, quotes, italics and blockquote lines.
  The rule is warn-only while it is new; where annotation-gate runs, its warning still fails the run.
  The check's allow comment exempts a deliberate use.
