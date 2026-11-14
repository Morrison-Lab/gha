- **The mlg render image has a recipe and a build script**
  ([#2006](https://github.com/Morrison-Lab/gha/issues/2006)).
  `condor-batch/image/mlg-ci.def` builds on `lds-ci.sif`, adds poppler-utils, and restores mlg's `renv.lock` library into `/opt/mlg-library`,
  and `condor-batch/image/build-mlg-ci.sh` builds it from an mlg ref on a host with Apptainer, then test-renders mlg in both profiles inside it.
  Rerun the script whenever mlg's `renv.lock` changes.
