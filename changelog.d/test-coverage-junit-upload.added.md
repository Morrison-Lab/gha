- **`test-coverage` gains an `upload-test-results` input** (#234). On by
  default, it generates a JUnit test-results report
  (`testthat::JunitReporter`) and uploads it to Codecov via
  `codecov/test-results-action`, powering Codecov's Test Analytics
  (failed/flaky-test reporting) -- separate from the existing Cobertura
  line-coverage upload, which only measures which lines ran, not which tests
  passed or failed. Matches the pre-migration behavior
  `UCD-SERG/serocalculator`'s bespoke `test-coverage.yaml` already had, so
  migrating to this reusable workflow no longer drops that feature.
