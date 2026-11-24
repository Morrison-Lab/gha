- **`check-double-inequalities`**
  (psw's "Avoiding double inequalities"):
  add a diff-scoped composite action and reusable workflow
  that fails a pull request adding math such as
  `a < x < b` or `0 \le p \le 1`,
  where interval membership (`x \in (a, b)`, `p \in [0, 1]`) says it once.
  A chain of three or more relations, or one with `=`, passes.
  Only lines a PR adds count, so existing pages never block.
