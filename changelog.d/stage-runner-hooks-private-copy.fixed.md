- **Runner hooks run from a private copy** --
  `scripts/check-runner-disk.sh` and `scripts/prune-runner-workdir.sh` now copy themselves and the
  scripts they call to a temp folder and run the copy, then remove it.
  Before this, a fast-forward of the runners' shared NFS checkout during a job made bash fail with
  "Stale file handle" ([#1589](https://github.com/Morrison-Lab/gha/issues/1589)).
