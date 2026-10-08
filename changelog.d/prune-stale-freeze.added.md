- **`preview` and `quarto-publish` keep the Quarto freeze cache safe to reuse.**
  After restoring `_freeze`, a new step drops the frozen results of each page
  whose own file, included subfiles, or named data files changed since the
  commit the cache was rendered from, and discards the whole cache when that
  commit cannot be read.
  `freeze: auto` notices only a page's own file, so consumers that edit
  subfiles had been adding the `clear freezer` label, which re-executed every
  page.
  With `freeze-cache: true` on `quarto-publish`, new PRs' previews also start
  from the default branch's frozen results instead of from scratch.
