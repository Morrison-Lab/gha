- **`lint-markdown` gains a split-table check and a `fail-on-table-splits`
  input** (#558).
  A blank line inside a GFM table ends the table block, so every row below it
  renders as literal pipe-delimited text.
  markdownlint's own table rules operate *within* a table block, so they
  structurally cannot see this -- measured, not assumed: against the broken
  file the bundled config reports 0 errors, and enabling every rule still
  fires nothing at the split, `MD058 blanks-around-tables` included.
  That is how `README.md`'s capability table carried the defect from `cacf1df`
  until #555, visible only to a person opening the file on GitHub.
  The check flags a run of pipe-prefixed lines that is not a table in its own
  right (no delimiter row) and sits blank-line-adjacent to another such run,
  so two deliberately adjacent tables are not reported.
