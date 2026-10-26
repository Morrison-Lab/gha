- `check-bibliography-dois.yml` takes a `preinstalled-toolchain` input that skips the R setup steps
  and installs the check's R packages with pak,
  so the check runs on a self-hosted runner that has R and no sudo.
