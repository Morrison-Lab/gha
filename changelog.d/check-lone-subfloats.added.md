- **`check-lone-subfloats`**
  ([#2173](https://github.com/Morrison-Lab/gha/issues/2173)):
  add a composite action and reusable workflow, diff-scoped and blocking,
  that flags a figure or table whose reader sees one subfigure or subtable.
  It flags a float with one subfloat,
  a float whose subfloats sit one per tab of a tabset,
  such as a language tabset whose chunks keep their `fig-` labels,
  and a chunk whose `fig-subcap` or `tbl-subcap` lists one entry.
