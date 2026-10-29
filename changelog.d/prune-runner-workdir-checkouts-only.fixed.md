- **The runner cleanup hook prunes only checkouts** --
  `scripts/prune-runner-workdir.sh` now deletes a folder in the work folder
  only when it holds a checkout (`<repo>/<repo>`).
  It used to treat every folder not named `_*` as one,
  so under 10 GB free it would delete `R/library`,
  where the self-hosted runners keep `R_LIBS_USER`
  ([#1352](https://github.com/Morrison-Lab/gha/issues/1352)).
