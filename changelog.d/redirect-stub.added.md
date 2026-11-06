- `check-format-output-files`:
  skip a page whose front matter sets `redirect-stub: true`,
  so an html-only redirect stub passes (gha#1544).
- `quarto-publish`:
  leave a page with `redirect-stub: true` out of every non-html render in a per-format publish,
  so an html-only redirect stub builds no slides and no PDF or Word file (gha#1544).
- `preview`:
  leave a page with `redirect-stub: true` out of every non-html render in the per-format preview loop (gha#1544).
