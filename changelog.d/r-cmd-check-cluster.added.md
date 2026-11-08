- **`cluster-check` job on `r-cmd-check.yml`**, off by default,
  runs the Linux check on a WWU cluster node through `condor-batch`.
  It adds the inputs `cluster-runs-on`, `cluster-head`, `cluster-image` and `cluster-image-file`.
  It installs the package dependencies into a library inside the job,
  because the cluster home quota is too small to restore them (gha#1640).
