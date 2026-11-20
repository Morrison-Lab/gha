- **`check-links` demotes an unreachable host off the diff**, as it does a 5xx.
  A timeout, or lychee's "Connection failed" network error, now fails a PR
  only when the link is on a line the PR adds, and is a warning otherwise.
  A web.stanford.edu outage on 2026-11-20 failed `link-checker` three times
  each on Morrison-Lab/mds#862, pds#474, and sds#642, none of which touched
  the links ([gha#2121](https://github.com/Morrison-Lab/gha/issues/2121)).
  A DNS error still blocks, since a misspelled host fails that way too.
  `fail-on-any-5xx` and `base-ref: all` keep every one blocking.
