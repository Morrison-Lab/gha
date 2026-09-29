- `preview`, `quarto-publish`: cache the Julia depot between runs with
  `julia-actions/cache` when `setup-julia: true`, keyed by Julia version,
  workflow, and job name to prevent repeated downloading and precompiling
  of RCall and Suppressor dependencies
  ([#974](https://github.com/Morrison-Lab/gha/issues/974)).
