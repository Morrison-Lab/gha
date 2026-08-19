- **`jules-review` no longer flags this repo's own reviewer workflow config as prompt injection**
  ([#517](https://github.com/Morrison-Lab/gha/issues/517)).
  `extra_instructions`, `prompt-addendum`, and comments quoting the action
  prompt in workflow files are treated as configuration under review.
  Untrusted PR description and comment text aimed at this review still counts.
