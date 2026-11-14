- When the cluster job of `r-cmd-check` runs, a new `plan` job drops the `ubuntu-*` cells of `config`, so the Linux check no longer also runs on a hosted machine.
  The macOS and Windows cells still run on hosted machines, and a `config` with no other cells skips the matrix job.
  The `plan` job runs on the cluster job's runner when the cluster job is on, and on `ubuntu-latest` otherwise ([gha#1640](https://github.com/Morrison-Lab/gha/issues/1640)).
