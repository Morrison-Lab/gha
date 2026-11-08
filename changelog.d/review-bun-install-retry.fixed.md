The Claude review no longer fails with no verdict when GitHub release downloads return 504 for a few minutes.
`run-claude-review-attempt` now downloads Bun itself with 8 retries 10 s apart, checks the pinned SHA-256, and passes the path to the action, which skips its own three-try install.
If that download fails, the action installs Bun as before (gha#1667).
