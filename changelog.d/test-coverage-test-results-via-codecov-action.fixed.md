- **`test-coverage` uploads JUnit test results with `codecov/codecov-action`**
  (#1012).
  The deprecated `codecov/test-results-action` began failing its upload
  with a TLS handshake error (SSL alert 40),
  which failed the `coverage` job on every PR.
  The step now uses the already-pinned `codecov/codecov-action`
  with `report_type: test_results`.
