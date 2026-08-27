- **`check-credential-shape`'s test suite runs off-runner again** (#688).
  The suite compared `wc -l` output as a string, and BSD/macOS `wc -l` pads
  with leading spaces, so all 14 cases failed on a maintainer's machine while
  CI stayed green.
  It now compares arithmetically, matching the sibling suites.
