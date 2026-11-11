- `check-exercise-background` now fails by default (`fail: true`).
  Whole-tree runs on the lds, mds, pds, sds, and psw notes, after gha#1914 and gha#1915, left only titles that name a term the body never states (gha#1481).
  Set `fail: false` to keep warnings.
