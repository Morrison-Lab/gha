- **`claude-code-review` reviewer now receives the PR's live `state`/`merged`
  fields as an authoritative fact** (#295).
  Previously the reviewer had no ground truth for whether a PR was open, and
  could hallucinate a "PR is closed/merged" verdict from a misread commit
  message on the PR's own branch --
  e.g. a routine `Merge remote-tracking branch 'origin/main' into <branch>`
  commit resolving a merge conflict, misread as evidence the PR itself had
  been merged.
  `claude-code-review.yml` now fetches `state` and `merged` once (in the
  existing "Stash and clear reviewers" step) and hands them to the reviewer
  prompt, with explicit instruction to trust that fact over any inference
  drawn from commit messages, branch names, or `git log` output.
