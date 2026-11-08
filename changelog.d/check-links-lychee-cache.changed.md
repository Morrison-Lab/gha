- **The `check-links` action** installs the pinned lychee 0.24.2 from the release cache
when the runner can use it, and falls back to `lycheeverse/lychee-action` otherwise,
so a release-host outage no longer blocks the link check (gha#1678).
