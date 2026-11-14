- **`quarto-publish` and `preview`: `cluster-render` skips the toolchain installs only on a self-hosted runner.**
  A private caller with no `CI_RUNNER` variable lands on `ubuntu-latest`,
  where the skipped installs left no R and the build failed with `Rscript: command not found`
  (Morrison-Lab/csci201 publish run 43082302218, a private repository).
  Such a job now installs R and Quarto and renders on the runner.
