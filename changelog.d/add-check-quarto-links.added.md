- **New `check-quarto-links` capability** (#960).
  Fails when a tracked `.qmd`, `.md`, or `.Rmd` file links to a page
  (`.qmd`, `.md`, `.Rmd`, `.ipynb`) that does not exist.
  Quarto only warns about such a link (`Unable to resolve link target`), and
  `check-links` (lychee) reads a `.qmd` as plain text, so it never checks a
  relative link from one (measured with lychee 0.24.2).
  Source level with no render, include-aware, and whole-tree.
  Also a default-on step in `check-quarto-website`, blocking under the
  suite's `fail`, so a consumer whose pages carry dead links goes red once the
  `@v3` tag slides.
