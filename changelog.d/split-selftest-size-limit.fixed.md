- **The selftest runs again**
  ([#1863](https://github.com/Morrison-Lab/gha/issues/1863)):
  `_selftest.yml` had passed GitHub's 500 KB workflow file limit,
  so no run of it started on any pull request.
  The content checks' jobs moved to a sibling workflow,
  `_selftest-content-checks.yml`, with the same triggers.
