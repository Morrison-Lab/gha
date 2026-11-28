- **The lds CI image recipe now installs `BART` and `dbarts`**
  ([#2217](https://github.com/Morrison-Lab/gha/issues/2217)).
  The lds render workflows install them for an ISL Lab 8.3.5 exercise,
  and a render in the image would stop at `library(BART)` without them.
  The image's `%test` section loads both, so a missing package fails the image build instead of a render.
  Rebuild `lds-ci.sif` from `condor-batch/image/lds-ci.def` to pick them up.
