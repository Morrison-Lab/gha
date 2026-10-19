- **New `check-paired-file-change` capability** ([#1123](https://github.com/Morrison-Lab/gha/issues/1123)).
  Fails a pull request that changes a file matching `trigger-paths`
  without also changing a file matching `required-paths`,
  unless the PR carries the `skip-label` label.
  Both path inputs are git pathspecs, matched against the PR's own diff.
  The label is read live from the API rather than from the stale event payload,
  and an empty `skip-label` never matches.
  `message` sets the failure annotation's text.
  The first caller is Morrison-Lab/macros,
  which requires `notation-choices.qmd` to change with `macros.qmd`
  ([macros#248](https://github.com/Morrison-Lab/macros/issues/248)).
