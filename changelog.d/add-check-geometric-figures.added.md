- `check-geometric-figures`:
  add a blocking check, scoped to the diff, as a composite action with a reusable workflow, that flags a geometric claim in prose
  (contour, ellipse, circle, level set, tangent line, hyperplane, decision boundary, perpendicular, "projects onto",
  "geometrically", right angle) that has no figure within `window` lines (default 40) or in an enclosing div,
  when a pull request adds the line (Ezra, 2026-11-16).
  It counts figures as `check-exm-figures` does, and `<!-- no-figure: reason -->` nearby exempts a claim no figure can show.
  It cannot tell whether the figure shows that claim, so psw's rule also goes into the Claude review prompt.
