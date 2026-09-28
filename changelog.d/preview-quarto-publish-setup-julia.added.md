- **`preview` and `quarto-publish` gain `setup-julia` and `julia-version`
  inputs** (#972).
  These let a knitr-rendered site execute `{julia}` chunks.
  `setup-julia: true` installs Julia with `julia-actions/setup-julia`, pinned the
  same way as in `r-cmd-check.yml`.
  When the R package JuliaCall is installed, a separate step then runs
  `JuliaCall::julia_setup()`, so JuliaCall's Julia dependencies (RCall and
  Suppressor) install before the render instead of partway through it.
  Callers add `any::JuliaCall` to `r-packages`.
  That step and the render set `R_LD_LIBRARY_PATH` to R's own `lib` directory.
  Otherwise R's `etc/ldpaths` puts `/usr/lib/x86_64-linux-gnu` first on
  `LD_LIBRARY_PATH`, Julia started by R loads the system libunwind, and any Julia
  exception, even a caught one, segfaults the process.
  That includes the one JuliaCall's display path throws and catches whenever a
  chunk line returns a value.
  Both inputs are optional and default to today's behaviour, and no
  `permissions:` change is needed.
  They ship at `@v3`, so a caller still pinning `preview.yml` or
  `quarto-publish.yml` at `@v2` has to move to `@v3` to use them.
