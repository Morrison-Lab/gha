- `check-format-output-files`, `quarto-publish`, and `preview`:
  a page whose front matter sets `redirect-stub: true` builds html only.
  The check accepts an html-only stub,
  and the per-format loops leave the stub out of every non-html render (gha#1544).
- `quarto-publish`:
  skip a redirect stub's non-html per-file renders (`per-file-formats`) too,
  and, when `quarto inspect` fails (gha#1214),
  append the stub exclusions to the project's own `render:` list
  rather than fail the publish.
  With neither, nothing is skipped.
