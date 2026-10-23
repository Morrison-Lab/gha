- **`preview` installs R packages as binaries and always saves the package cache** (#1174).
  Posit Package Manager is now the only repository for the non-renv install,
  so pak no longer resolves CRAN source tarballs.
  `setup-r-dependencies` runs with `cache: always`,
  so a build that fails or is cancelled at its time limit still saves the packages it installed.
