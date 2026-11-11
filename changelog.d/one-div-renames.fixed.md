- `check-one-div-per-subfile` no longer flags a pull request that only moves files:
  a file moved into a `_subfiles` directory from outside the globs is read as a rename,
  and an `include` line that changes only its path to follow a renamed file counts as moved
  (Morrison-Lab/rme#1482).
