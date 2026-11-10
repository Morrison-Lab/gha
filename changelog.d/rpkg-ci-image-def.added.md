- `condor-batch/image/rpkg-ci.def`: an Apptainer recipe for R CMD check, covr, and pkgdown jobs on the clusters, built from `lds-ci.sif`.
  A package's own dependencies install into a per-job library, not into the image (gha#1640).
