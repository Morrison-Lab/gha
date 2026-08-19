- **New `check-new-line-breaks` capability** (composite action +
  `check-new-line-breaks.yml` reusable workflow) (#299).
  Diff-scoped check that flags newly-added Markdown lines packing more than
  one sentence/clause onto a single source line -- the "semantic line
  breaks" convention. Only checks lines a PR's diff actually adds, so it
  never reflags a corpus's pre-existing long-line drift; pairs well with
  `lint-markdown` when markdownlint's MD013 (line-length) is disabled for
  exactly that reason.
  Blocking by default (`fail: true`).
  Ported from `d-morrison/ai-config`'s `scripts/check-new-line-breaks.py`.
