- `preview` and `quarto-publish`: a subfile included from another subfile now counts as a dependency of the page that renders it (#2002).
  `prune-stale-freeze.py` resolved every relative include from the file that holds it,
  but `quarto render` resolves an include nested in a subfile from the top-level page's directory.
  So an edit to such a file reached no page:
  the incremental preview planned "0 stale pages" and served the cached page,
  and the publish kept the page's stale freeze.
  The walker now records both candidates.
- `preview`: the incremental planner now renders the whole site when a changed `_`-prefixed `.qmd` reaches no rendered page,
  instead of treating it as unused,
  because such a file only matters through an include the walker may not have followed.
