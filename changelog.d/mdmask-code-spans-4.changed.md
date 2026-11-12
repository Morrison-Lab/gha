- `check-page-length`, `check-quarto-links`, and `student-qmd` now take their code-span pattern
  from `check-common/mdmask.py` (gha#1856),
  so `student-qmd` needs `check-common` beside it, as the checks already do.
  A span now closes only on a backtick run of the same length.
