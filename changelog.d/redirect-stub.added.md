- `check-format-output-files`, `quarto-publish` and `preview`:
  a page whose front matter sets `redirect-stub: true` builds html only.
  The check accepts an html-only stub,
  and the per-format loops leave the stub out of every non-html render (gha#1544).
