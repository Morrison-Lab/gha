- `check-non-standard-chars` now scans only files git tracks (falling back to a
  file-system walk outside a git checkout).
  Persistent self-hosted runners keep untracked leftovers, such as a submodule
  an earlier job populated, and the check reported characters in them
  ([#1383](https://github.com/Morrison-Lab/gha/issues/1383)).
