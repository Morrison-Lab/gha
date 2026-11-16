- **One image recipe and one composite serve every grading repository's cluster render**, in place of per-repository copies.
  `condor-batch/image/repo-ci.def` and `condor-batch/image/build-repo-ci.sh <repo> [ref] [image-dir]` build `<repo>-ci.sif` for any repository:
  `lds-ci.sif` plus poppler-utils, the `nameref` and `xpatch` LaTeX packages, the repository's `renv.lock` library when it has one,
  and the packages and test the repository itself lists under `.github/ci-image/`.
  They replace `mlg-ci.def` and `build-mlg-ci.sh`, which are removed.
  The `student-copy-render` composite (`.github/actions/student-copy-render`) runs a student-copy check as one HTCondor job through `condor-batch`:
  both profiles, each question on its own, then the repository's check.
  It takes the document and question lists, so a repository that renders only what a PR changed (mcsg) uses it as well as one that renders everything (mlg).
