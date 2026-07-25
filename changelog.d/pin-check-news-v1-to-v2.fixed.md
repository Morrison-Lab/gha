- **Corrected `check-news.yml`'s documented pin from `@v1` to `@v2`** across
  `README.md`, `website/workflows.qmd`, `website/reference/check-news.qmd`,
  `examples/check-news.yml`, and `CLAUDE.md`. The versioning docs had
  (incorrectly) grouped `check-news.yml` with the workflows "unchanged since
  the freeze," but it actually gained a configurable `no-changelog-label`
  input at #143 -- a fix that only exists past the frozen `@v1` tag. A
  consumer following the documented `@v1` pin (`UCD-SERG/serocalculator`)
  reproduced #143's original bug: applying its own `no-changelog` label did
  not skip the changelog check, since `@v1` never picked up the fix meant to
  make that work.
