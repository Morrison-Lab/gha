- **`.github/workflows/claude.yml` now checks out the PR branch before R/renv setup**
  ([#435](https://github.com/Morrison-Lab/gha/issues/435)).
  Previously, `Checkout PR branch` ran after `Restore renv` and `Install R dependencies`,
  so `renv::restore()` and `setup-r-dependencies` read `renv.lock` and `DESCRIPTION` from
  the base branch (`main`) rather than the PR branch. Moving the PR branch checkout earlier
  ensures dependencies are restored from the PR's own tree.
