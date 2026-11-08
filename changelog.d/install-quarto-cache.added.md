- **`install-quarto` composite** installs a pinned Quarto release from the release cache,
  so a release-host outage does not block the job.
  It falls back to `quarto-dev/quarto-actions/setup` on a runner without passwordless `sudo`,
  on a platform other than Linux amd64, and for a version with no pinned digest (gha#1678).
