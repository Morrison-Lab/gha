- A cluster render in `preview` and `quarto-publish` now installs the caller's `r-packages` that the image lacks, into a library in the job's scratch directory, before it renders.
  CRAN names (`any::`, `cran::`, or bare), `deps::<path>`, and GitHub `owner/repo` entries are installed.
  Other forms are reported and skipped.
  So one cluster image can serve every repository, without a per-repository image ([gha#2007](https://github.com/Morrison-Lab/gha/issues/2007)).
