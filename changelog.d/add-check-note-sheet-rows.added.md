- `check-note-sheet-rows/` (Python, stdlib only, gha#1164) bundles the composite action, script, and pytest suite
  for flagging a note-sheet table row that holds more than one concept: notation in a label (unless the label links to the term's definition),
  a label joining two concepts with a comma or "and", or two formulas in one cell.
  It reads pipe tables in `*note-sheet*.qmd` files, takes the same diff model as `check-one-div-per-subfile`,
  and is warn-only by default (`fail: false`), because the heuristics also report a label such as `Sample MSE, matrix form`.
  The rule is PSW's "Give each concept in a note sheet its own row" (Ezra, 2026-10-22).
