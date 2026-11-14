- The cluster job of `test-coverage` now uploads its Cobertura report to Codecov, before the `min-coverage` threshold, as the runner job does, so turning the cluster on no longer stops Codecov reporting.
  It writes no JUnit report, so `upload-test-results` does not apply to it ([gha#1640](https://github.com/Morrison-Lab/gha/issues/1640)).
