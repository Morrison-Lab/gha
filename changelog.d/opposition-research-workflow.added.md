- **Add reusable opposition-research workflow and recurring schedule**
  (#868).
  Adds `opposition-research.yml`,
  a reusable workflow that automates opposition research on competitor products,
  frameworks, and repositories.
  Mines public community surfaces
  (issues, discussions, forums)
  for user-demanded capabilities,
  filters for repository scope,
  deduplicates against existing issues,
  and files high-signal opportunities as tracked issues.
  Adds `.github/workflows/oppo-schedule.yml` to run automated weekly research
  against peer GitHub Actions suites for `Morrison-Lab/gha`.
