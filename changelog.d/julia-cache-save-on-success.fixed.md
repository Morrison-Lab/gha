- **`preview` and `quarto-publish`: the Julia cache saves only on success.**
  `julia-actions/cache` saves on failure and on cancel by default,
  so a build cancelled partway through the JuliaCall install stored a half-installed depot.
  Every later build on that ref restored it and failed with
  "Path to conda environment is not valid" and "RCall not properly installed",
  and each failed run saved the broken depot again, so a re-run never recovered.
  The step now sets `save-always: false`.
  The cache name also gains `-v2`, so depots saved before this change are never restored.
  The first build after it on each ref installs Julia from scratch once.
  Callers get it when the tag they pin slides to include this change.
