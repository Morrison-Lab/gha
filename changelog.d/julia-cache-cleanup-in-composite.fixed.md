- `preview`, `quarto-publish`: stop the Julia cache's post step from logging
  `SystemError: opening file .../handle_caches.jl: No such file or directory`.
  `julia-actions/cache` finds that script through `GITHUB_ACTION_PATH`,
  which points at the enclosing composite in a nested post step, so its
  old-cache cleanup could never run here.
  It is now off
  (`delete-old-caches: 'false'`)
  ([#1023](https://github.com/Morrison-Lab/gha/issues/1023)).
- `preview`, `quarto-publish`: stop every Julia session from logging
  `Path to conda environment is not valid` when the Julia depot comes from
  the cache.
  RCall depends on Conda.jl, whose build creates an empty `conda/3/<arch>`
  directory that `julia-actions/cache` does not restore, so the JuliaCall
  setup step now recreates it
  ([#1023](https://github.com/Morrison-Lab/gha/issues/1023)).
