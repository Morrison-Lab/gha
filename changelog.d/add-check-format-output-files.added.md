- `check-format-output-files`:
  add a blocking composite action that flags a Quarto page
  whose `format:` omits, or gives no `output-file` to, a format that a per-format publish renders.
  `quarto render --to revealjs` renders every page, even one that does not list `revealjs`,
  under the default name, so the deck replaced `linear-algebra.html`, `algebra.html` and `calculus.html` on the mds site.
  The check reads each page's front matter with no YAML dependency;
  `formats` sets which formats to require (default `revealjs pdf docx`).
