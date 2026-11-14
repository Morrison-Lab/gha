- `r-cmd-check` and `test-coverage` run their cluster jobs on a private repository whose `CI_CLUSTER_CHECK` variable is `true`, even when the caller leaves `cluster-check` off.
  The image inputs fall back to `CI_CLUSTER_RPKG_IMAGE` and `CI_CLUSTER_RPKG_IMAGE_FILE`, and the job reads `CI_RUNNER_CLUSTER` before `CI_RUNNER`.
  An empty `cluster-head` (the new default) spreads the jobs over the CI cluster heads, as `preview` does since [gha#1518](https://github.com/Morrison-Lab/gha/issues/1518) ([gha#1640](https://github.com/Morrison-Lab/gha/issues/1640)).
