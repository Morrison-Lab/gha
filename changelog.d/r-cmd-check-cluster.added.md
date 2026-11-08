The `r-cmd-check.yml` reusable workflow has an opt-in `cluster-check` job that runs the Linux check on a WWU cluster node through `condor-batch`.
It is off by default and adds the inputs `cluster-runs-on`, `cluster-head`, `cluster-image`, and `cluster-image-file`.
It installs the package dependencies into a library inside the job, because the cluster home quota is too small to restore them (gha#1640).
