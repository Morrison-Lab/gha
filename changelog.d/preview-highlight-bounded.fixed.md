- **`preview`: change highlighting no longer hangs on pages with code
  chunks followed by htmlwidgets**
  ([#975](https://github.com/Morrison-Lab/gha/issues/975)).
  The element regex's `<p` also matched `<pre>`, and since no `</p>` closes
  a `<pre>`, one "element" ran through the code chunk and any widget
  `<script>` JSON after it to the next paragraph's `</p>`: megabytes of text
  whose character-level diff never finished.
  The regex now requires a word boundary after the tag name, so the
  paragraph after a code chunk is compared, and highlighted, on its own.
  The page similarity is computed over word tokens of the page markup with
  `<script>`/`<style>` blocks removed, rather than character by character
  over the whole page, those blocks included.
  As a backstop, an element that embeds `<script>`/`<style>` or has more
  than `HIGHLIGHT_MAX_ELEMENT_CHARS` (default 20000) characters of text is
  left out of the comparison, with a notice naming the page and each
  element by its visible text.
  Unchanged elements are matched by exact text, and difflib's
  `quick_ratio()` bounds prune the pairwise search without changing its
  result.
  A per-page and a whole-run time budget (`HIGHLIGHT_PAGE_BUDGET_SECONDS`,
  default 60; `HIGHLIGHT_TOTAL_BUDGET_SECONDS`, default 300) leave a page
  unhighlighted with a warning instead of consuming the job.
