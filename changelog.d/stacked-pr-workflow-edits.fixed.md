- **Hardened workflow-edit detection and review dispatch on stacked PRs** (#916).
  `list-pr-changed-files.sh` now fails closed when a PR targets a non-default base branch,
  preventing review dispatch from executing untrusted workflow YAML inherited from earlier stack layers.
  Review workflows and dispatch helpers detect stacked PRs and skip manual review dispatch,
  allowing push-triggered reviews with restored default-branch workflows to evaluate the PR head safely.
