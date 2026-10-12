- Docs: the `claude-code-review` permissions notes in `README.md`,
  `website/permissions.qmd`, and its reference page now say what a
  Dependabot `@v2` to `@v3` bump does to a caller that does not grant
  `checks: read`.
  The run ends in `startup_failure` and the PR shows no review check at all,
  so the grant belongs in the bump PR itself
  ([#1006](https://github.com/Morrison-Lab/gha/issues/1006)).
