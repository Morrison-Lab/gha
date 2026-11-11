- `check-exercise-background` now fails by default (`fail: true`).
  Whole-tree runs on the lds, mds, pds, sds, and psw notes, after the fixes in the two PRs before this one, left only titles that name a term the body never states (gha#1481).
  Set `fail: false` to keep warnings.
