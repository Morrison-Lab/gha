- **`preview`: change highlighting no longer hangs on htmlwidget pages**
  ([#975](https://github.com/Morrison-Lab/gha/issues/975)).
  The page similarity is now computed over word tokens of the visible prose
  rather than character by character over the whole page, `<script>`/`<style>`
  blocks included.
  Elements whose regex match spans a `<script>`/`<style>` block, or whose text
  exceeds `HIGHLIGHT_MAX_ELEMENT_CHARS` (default 20000), are left out of the
  comparison and never highlighted.
  Unchanged elements are matched by exact text, and difflib's
  `quick_ratio()` bounds prune the pairwise search without changing its
  result.
  A per-page and a whole-run time budget (`HIGHLIGHT_PAGE_BUDGET_SECONDS`,
  default 60; `HIGHLIGHT_TOTAL_BUDGET_SECONDS`, default 300) leave a page
  unhighlighted with a warning instead of consuming the job.
