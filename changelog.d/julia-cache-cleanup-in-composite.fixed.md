- `preview`, `quarto-publish`: stop the Julia cache's post step from logging
  `SystemError: opening file .../handle_caches.jl: No such file or directory`.
  `julia-actions/cache` finds that script through `GITHUB_ACTION_PATH`,
  which points at the enclosing composite in a nested post step, so its
  old-cache cleanup could never run here.
  It is now off
  (`delete-old-caches: 'false'`)
  ([#1023](https://github.com/Morrison-Lab/gha/issues/1023)).
