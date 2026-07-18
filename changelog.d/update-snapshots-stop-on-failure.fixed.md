- **`update-snapshots` now fails the job when the suite still fails after
  accepting snapshots** (#272). The verification re-run called bare
  `devtools::test()`, whose default is `stop_on_failure = FALSE`, so a suite
  still failing after `testthat::snapshot_accept()` exited 0 and the broken
  snapshots were committed and pushed anyway. The re-run now passes
  `stop_on_failure = TRUE`, failing the job before the commit-and-push
  steps. Surfaced by review on the new reference page, whose description of
  the verification gate contradicted the actual behavior.
