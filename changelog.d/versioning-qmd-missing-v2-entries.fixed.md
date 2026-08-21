- **`website/versioning.qmd`'s first `@v2` list was missing three capabilities**
  (#538).
  The page states the `@v1`/`@v2` split twice, and the two lists had drifted:
  the top-of-page paragraph omitted `small-model-agent.yml` and
  `check-ai-tells.yml` from the "only ever shipped at `@v2`" group, and
  `check-news.yml` from the "pin to `@v2`" group.
  A consumer reading only that paragraph would pin the first two to a tag where
  they do not exist, and leave the third at `@v1` without the
  `no-changelog-label` input it gained in gha#143.
  Both lists now name the same 34 workflows.
