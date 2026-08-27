- **Bot reviews of PRs that edit workflow files run against default-branch
  copies of those files** (#598).
  A PR that touched `.github/workflows/*.yml` used to skip the Claude review
  (or fail `claude-code-action`'s OIDC workflow-content check) so the job would
  not execute untrusted YAML from the PR head.
  `claude-code-review.yml` now restores `.github/workflows/` from the default
  branch after checkout and passes `github_token` so that check is skipped.
  Dispatched reviews omit `--ref` so GitHub itself executes the default-branch
  caller.
  A files-list response shorter than the PR's `changed_files` count is
  treated as incomplete (GitHub caps that endpoint at 3000 files), so a
  large PR cannot hide a workflow edit behind the cap.
  The restore-failure skip notice names an incomplete file list rather
  than a fake workflow path when the PR files endpoint fails or is
  truncated.
  `self_mod` now means the restore failed, not that the PR merely edited a
  workflow file.
  Automatic `pull_request` reviews of a PR that edits the *caller* still
  execute that caller YAML --- GitHub has already selected it --- and this
  does not switch to `pull_request_target`.
  A no-`--ref` dispatch's check-runs land on the default branch (#285); the
  review comment still posts on the PR.
