- `check-avoided-words` fails on a line a pull request adds
  that names notation with "write", as in "write $X$ for", "writing $X$ for",
  or "is written $X$" (psw#671, Ezra 2026-11-16: name notation with "denote").
  "Write the sum as $S$" and "write $X$ in terms of $Y$" pass.
  It fails by default; only added lines are read, so existing uses do not trip it.
