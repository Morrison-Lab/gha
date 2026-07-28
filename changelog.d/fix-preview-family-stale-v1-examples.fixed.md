- **Example stubs and reference docs for the preview family and
  `quarto-publish` pinned the frozen `@v1` tag while documenting `@v2`
  behavior.** `examples/preview.yml`, `examples/preview-deploy.yml`,
  `examples/cleanup-pr-previews.yml`, `examples/quarto-publish.yml`, and their
  matching `website/reference/*.qmd` pages all pinned `@v1`. `@v1` was frozen
  at the pre-`2.0.0` snapshot and never picked up `cleanup-pr-previews`'s
  `compact-history` input at all — the example's own commented-out
  `compact-history: true` line would fail GitHub Actions' `workflow_call`
  input validation if pinned `@v1` and uncommented. `quarto-publish.yml`'s
  reference page described the `gh-pages` branch deploy throughout but pinned
  `@v1`, which actually deploys via the GitHub Actions Pages artifact and
  needs different permissions (`pages: write` + `id-token: write`, not
  `contents: write`) — confirmed against `d-morrison/rme`, the family's
  original and most mature consumer, which pins `@v2` throughout. Bumped every
  stale pin to `@v2`, added the missing `compact-history` input row and
  example line to `website/reference/cleanup-pr-previews.qmd`, and reworded
  the `README.md` / `website/workflows.qmd` / `website/versioning.qmd` /
  `website/index.qmd` / `CLAUDE.md` versioning notes to scope the `@v2`
  recommendation to these four capabilities plus the pre-existing
  `test-coverage`/`check-equation-renders` exceptions, rather than claiming
  `@v1` (or `@v2`) as the default for every workflow. The remaining
  capabilities' stubs stay at `@v1`, tracked for a future audit in
  [gha#182](https://github.com/Morrison-Lab/gha/issues/182).
- **Registered `d-morrison/ai-config` in `REVDEPS.md`** as a consumer of
  `quarto-publish`, `preview`, `preview-deploy`, and `cleanup-pr-previews`
  ([ai-config#401](https://github.com/Morrison-Lab/ai-config/issues/401)).
