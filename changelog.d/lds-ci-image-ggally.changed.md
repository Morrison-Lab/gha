- **The lds CI image recipe now installs `GGally`**
  ([#1431](https://github.com/Morrison-Lab/gha/issues/1431)).
  `classification-lab.qmd` loads it, and a render in the image stopped there without it.
  The image's `%test` section loads it too, so a missing package fails the image build instead of a render.
  Rebuild `lds-ci.sif` from `condor-batch/image/lds-ci.def` to pick it up.
