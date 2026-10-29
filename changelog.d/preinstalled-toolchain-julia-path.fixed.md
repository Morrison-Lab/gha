- **`preview` and `quarto-publish` also find the runner's Julia and TinyTeX when
  `preinstalled-toolchain` is `true`.**
  The Quarto-only PATH step left `julia: command not found` in the JuliaCall
  setup, because `setup-julia` is skipped with a preinstalled toolchain.
  The step now adds the newest `~/opt/julia-<version>/bin` (or `~/.juliaup/bin`)
  and the `~/.TinyTeX/bin/<platform>` directory, as well as Quarto,
  for each tool that is not already on `PATH`.
