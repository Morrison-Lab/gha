- `check-format-output-files`:
  add a blocking composite action that flags a Quarto page whose `format:`
  omits, or gives no `output-file` to, a format that a per-format publish renders.
  `quarto render --to revealjs` renders every page under the default name,
  so the deck replaced `linear-algebra.html` on the mds site.
