- `claude-code-review`: the reusable review workflow no longer posts each
  review twice. The reviewer agent's `gh pr comment` self-post
  (`claude[bot]`) is now explicitly denied in `run-claude-review-attempt`'s
  `--disallowedTools`, and the reviewer prompt tells the agent to output its
  review rather than post it -- so the workflow's own "Post review comment"
  step (`github-actions[bot]`) is the sole poster. This also retires the
  raw-`gh pr comment`-republishing class (#312, #318, #381): with the tool
  denied, the agent never issues the command there was nothing to republish.
  As part of the same change, the prior-review-context fetch and the
  older-comment collapse step now match the `github-actions[bot]` author the
  workflow actually posts under (they previously matched `claude[bot]` alone,
  so the collapse step silently folded nothing in agent mode). Closes #381.
