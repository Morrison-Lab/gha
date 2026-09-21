- **Add reusable check-dependency-updates workflow and recurring schedule**
  (#869).
  Adds `check-dependency-updates.yml`,
  a reusable workflow that automates dependency freshness audits across GitHub
  Actions pins, renv packages, tool versions, and submodules.
  Mines changelogs and release notes for high-value capabilities and fixes,
  filters for relevance and scope,
  deduplicates against existing issues,
  and files actionable opportunity and to-do issues.
  Adds `.github/workflows/check-dependency-updates-schedule.yml`
  to run automated weekly audits for `Morrison-Lab/gha`.
