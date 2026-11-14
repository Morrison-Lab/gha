- `preview` and `quarto-publish` render on the cluster in a private repository whose `CI_CLUSTER_RENDER` variable is `true`, even when the caller leaves `cluster-render` off, and their build job then takes its runner from `CI_RUNNER_CLUSTER` before `CI_RUNNER_HEAVY` and `CI_RUNNER`.
  The variable never applies with `use-renv` or `setup-chrome`, or to a preview PR labelled `preview:runner`, and a repository opts out by setting its own `CI_CLUSTER_RENDER` to `false`.
  `CI_RUNNER_CLUSTER` chooses only which runner submits the job:
  without it, the render is still submitted to the cluster from the `CI_RUNNER_HEAVY` or `CI_RUNNER` runner.
  With `CI_CLUSTER_RENDER` unset nothing changes ([gha#2007](https://github.com/Morrison-Lab/gha/issues/2007)).
