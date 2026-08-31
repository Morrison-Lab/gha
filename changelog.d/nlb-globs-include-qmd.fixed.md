- `_selftest.yml` and `check-diff-scoped.sh`: scan `.qmd` files in `check-new-line-breaks` (#750).
  `_selftest.yml` now passes `globs: '*.md *.qmd'` to the `new-line-breaks` jobs,
  and `check-diff-scoped.sh` defaults `NLB_GLOBS` to `*.md *.qmd`,
  ensuring newly-added prose across `website/` is scanned for semantic line breaks.
