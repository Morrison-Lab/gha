- In `cleanup-pr-previews.yml`, wait for the base branch's publish/deploy workflow to succeed before removing preview directories for merged pull requests ([gha#994](https://github.com/Morrison-Lab/gha/issues/994)).
  Adds `publish-workflow` (defaulting to auto-detection of workflows matching `publish`, `deploy`, or `pages-build-deployment`) and `wait-for-publish` (default `true`).
  If the base-branch publish run for the merge commit is queued, in progress, or failed without a subsequent successful publish, the preview directory is retained instead of being pruned immediately.
