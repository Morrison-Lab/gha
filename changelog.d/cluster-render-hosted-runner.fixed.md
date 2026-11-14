- **`quarto-publish` and `preview`: `cluster-render` skips the toolchain installs only on a self-hosted runner.**
  A private caller with no `CI_RUNNER` variable lands on `ubuntu-latest`,
  where the skipped installs left no R and the build failed with `Rscript: command not found`
  ([csci201 run 43082302218](https://github.com/Morrison-Lab/csci201/actions/runs/43082302218/job/130737685322)).
  Such a job now installs R and Quarto and renders on the runner.
