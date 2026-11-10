- `check-links` retries the cached lychee install once after 60 s
  before it falls back to `lychee-action`,
  so a release-host burst shorter than a minute no longer sends the job to the download that fails
  ([gha#1667](https://github.com/Morrison-Lab/gha/issues/1667)).
