- **check-dependency-updates: stop failing on the OIDC token exchange** (gha#1407).
  The audit step now forwards the job's `github_token` to `claude-code-action`,
  which skips the action's OIDC App-token exchange.
  Without it, the step failed with "Could not fetch an OIDC token",
  and every weekly scheduled run failed from 2026-09-28 to 2026-11-02.
  The `model` input now goes through `claude_args` (`--model`),
  because `claude-code-action` has no `model` input and ignored it with a warning.
