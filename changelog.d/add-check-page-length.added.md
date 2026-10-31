- `check-page-length`:
  add a diff-scoped, warn-only composite action and reusable workflow that flags a Quarto page
  a pull request adds to when the page, with its `include` shortcodes expanded,
  has more than 600 math expressions or 5000 source lines.
  The goal is that a page loads and finishes rendering its math in under 5 seconds,
  and that its scroll bar is not at its smallest length (Ezra, 2026-10-31).
  The check runs without a browser, so the two limits are proxies, tunable with `max-math` and `max-lines`.
  Like `check-heading-levels` it scopes to touched pages, skips rather than scanning the whole tree
  when there is no base to diff against, and has a `whole-tree` mode that measures a corpus.
  `<!-- check-page-length: allow -->` exempts a page.
