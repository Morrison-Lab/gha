- `check-avoided-words` warns on a line a pull request adds
  that says "intercept" or "intercepts" without saying which concept it means:
  the intercept of a function, its value at zero input,
  or the intercept term of an expression, its constant term
  (Ezra, 2026-11-22; psw#701).
  These forms pass: "intercept term(s)", "intercept(s) of", "y-intercept", and "x intercept".
  So do a link to `#def-intercept` or `#def-intercept-term`, hyphenated compounds, and ids,
  as well as code, math, quotes, italics, and blockquote lines.
  The rule is warn-only while it is new.
  Where annotation-gate runs, its warning still fails the run.
  The check's allow comment exempts a deliberate use.
