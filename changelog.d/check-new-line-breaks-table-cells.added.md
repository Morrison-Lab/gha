- **`check-new-line-breaks`: a `table-cells` input checks added pipe-table rows.**
  The check skipped table rows, so a row whose cell packed a whole paragraph passed.
  A pipe-table row cannot take a line break, so such a row makes an unreadable diff.
  With `table-cells: true`, each cell of an added row gets the sentence and clause rules.
  The row is flagged when a cell fails, and the fix is to move the prose out of the table.
  It is off by default, so no caller starts failing without opting in.
  Requested for Morrison-Lab/mlg, whose README tables hold paragraph-long cells.
