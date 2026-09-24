- The `@v3` reusable workflows and bundle composites now call this repo's own
  composites and workflows at `@v3` rather than `@v2` (#925).
  `@v2` froze before `checkout-reference-repos`, `student-qmd`, the
  `check-*` bundles and several other pieces existed,
  so an `@v3` caller of any workflow referencing one of them failed at job
  preparation with `Can't find 'action.yml'`.
  The two scheduled dogfood callers of `check-dependency-updates.yml` and
  `opposition-research.yml`, which do not exist at `@v2`, now call them at
  `@v3`; their permission grants already match.
