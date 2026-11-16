- **One image recipe serves every repository's cluster render**, in place of per-repository copies
  ([#2064](https://github.com/Morrison-Lab/gha/issues/2064)).
  `condor-batch/image/repo-ci.def` and `condor-batch/image/build-repo-ci.sh <repo> [ref] [image-dir]` build `<repo>-ci.sif` for any repository:
  `lds-ci.sif` plus poppler-utils, the `nameref` and `xpatch` LaTeX packages, the repository's `renv.lock` library when it has one,
  and the packages the repository lists in `.github/ci-image/apt-packages.txt` and `tlmgr-packages.txt`.
  The build runs the repository's `.github/ci-image/test.sh` inside the new image and keeps the old image when it fails or is missing.
  They replace `mlg-ci.def` and `build-mlg-ci.sh`, which are removed.
