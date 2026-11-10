- `condor-batch/image/rpkg-ci.def`: sets `RSTUDIO_PANDOC` to Quarto's bundled pandoc, so `R CMD build` can build R Markdown vignettes inside the image.
  A cold `R CMD check` of rampp on a cluster node failed with "Pandoc is required to build R Markdown vignettes" until the variable was set by hand (gha#1640).
