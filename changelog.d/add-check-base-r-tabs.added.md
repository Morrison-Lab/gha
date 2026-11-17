- `check-base-r-tabs`:
  add a diff-scoped composite action and reusable workflow
  that fails a pull request adding or editing a `panel-tabset`
  with an "R (tidymodels)" tab and no base R tab
  (Ezra, 2026-11-17, Morrison-Lab/lds#2708).
  An untouched tabset is not reflagged,
  and a run with no base to diff against is skipped.
  `<!-- base-r-tab: none: reason -->` opts a tabset out.
  It fails by default (`fail: false` warns).
