- **New `request-dependabot-review.yml` reusable workflow** (#252). Requests
  review from a configured list of reviewers when a PR's author matches a bot
  actor (`dependabot[bot]` by default), so scheduled dependency-bump PRs don't
  merge without a human look — `dependabot.yml`'s own `reviewers:` config
  option was retired by GitHub in favor of CODEOWNERS, which can't scope a
  rule to bot-authored PRs only. This repo now dogfoods it against its own
  Dependabot PRs (`.github/workflows/dependabot-review.yml`). The
  comma-separated `reviewers` list is split and trimmed by a new
  `build-reviewer-args` composite action, with offline and end-to-end
  selftest coverage (gha#253 review).
