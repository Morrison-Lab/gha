- **`preview` and `quarto-publish` rebuild RCall against the current R before the JuliaCall setup.**
  The restored Julia cache keeps the R library path RCall recorded when it was built,
  so after R 4.6.2 replaced 4.6.1 every Julia page failed with
  `Could not find library /opt/R/4.6.1/lib/R/lib/libR.so`.
  The setup step now runs `Pkg.build("RCall")` with `R_HOME` set to the current R
  when RCall is already installed.
