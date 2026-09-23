- **`claude-code-review.yml` allows retry on action short-circuits with non-zero exits** (#905).
  The same-prompt retry condition now admits short-circuits
  where no execution file was written,
  even if the action step exited non-zero (`outcome == 'failure'`),
  while continuing to protect against retrying hard SDK errors
  where work was billed.
