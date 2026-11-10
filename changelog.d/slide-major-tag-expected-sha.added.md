- **`slide-major-tag.yml` takes an optional `expected_sha` input**
  ([#1834](https://github.com/Morrison-Lab/gha/issues/1834)).
  When it is set, the run fails unless the commit it would tag is that commit,
  so a merge that lands after the dispatcher's checks cannot ship an unchecked commit.
  Without it, the workflow behaves as before.
