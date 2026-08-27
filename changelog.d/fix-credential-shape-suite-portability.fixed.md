- **`check-credential-shape`'s test suite runs off-runner** (#688).
  The suite compared `wc -l` output as a string, and BSD/macOS `wc -l` pads
  with leading spaces, so all 14 cases failed on a maintainer's machine while
  CI stayed green.
  It now compares arithmetically.

- **`report-review-failure`'s `failure-kind` description gains a drift note**
  (#688).
  The field is not validated against an enum, so the list must be kept in step
  with `compose-review-failure-report.sh`'s own arms by hand.
