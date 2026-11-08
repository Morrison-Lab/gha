- `condor-batch/image/rpkg-ci.def`: an Apptainer recipe, built from `lds-ci.sif`, for R CMD check, covr and pkgdown jobs on the clusters.
  A package's own dependencies install into a per-job library, not into the image (gha#1640).
