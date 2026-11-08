- **The epi204 render image has a recipe and a build script**
  ([#1638](https://github.com/Morrison-Lab/gha/issues/1638)).
  `condor-batch/image/epi204-ci.def` builds on `lds-ci.sif`, restores the `renv.lock` library into `/opt/epi204-library` and installs the epi204 package,
  and `condor-batch/image/build-epi204-ci.sh` builds it from an epi204 ref on a host with Apptainer.
  Rerun the script whenever epi204's `renv.lock` changes.
