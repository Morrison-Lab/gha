- **`quarto-publish` with `formats` keeps every format's `site_libs` files.**
  Each later per-format render deleted the earlier formats' supporting files,
  so the published HTML pages lost their CSS and JavaScript
  (`bootstrap`, `quarto-nav` and `quarto-search` after a `revealjs` render).
  The action now collects `site_libs` after each render
  and restores the union once the split renders finish.
