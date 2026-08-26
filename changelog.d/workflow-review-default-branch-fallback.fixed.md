- **Bot reviews of PRs that edit workflow files run against default-branch
  copies of those files** (#598).
  A PR that touched `.github/workflows/*.yml` used to skip the Claude review
  (or fail `claude-code-action`'s OIDC workflow-content check) so the job would
  not execute untrusted YAML from the PR head.
  `claude-code-review.yml` now restores `.github/workflows/` from the default
  branch after checkout and passes `github_token` so that check is skipped.
  Dispatched reviews omit `--ref` so GitHub itself executes the default-branch
  caller.
  `self_mod` now means the restore failed, not that the PR merely edited a
  workflow file.
  Automatic `pull_request` reviews of a PR that edits the *caller* still
  execute that caller YAML --- GitHub has already selected it --- and this
  does not switch to `pull_request_target`.
  A no-`--ref` dispatch's check-runs land on the default branch (#285); the
  review comment still posts on the PR.
