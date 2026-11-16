- `check-avoided-words` warns on a line a pull request adds
  that names notation with "write", as in "write $X$ for", "writing $X$ for",
  or "is written $X$" (psw#671, Ezra 2026-11-16: name notation with "denote").
  "Write the sum as $S$" and "write $X$ in terms of $Y$" pass.
  The rule is warn-only while it is new: it never fails the run, even with `fail` on.
