- **`claude-code-review` and `build-quota-skip-notice` report the Claude account email or identity on quota-skip notices** (#1018).
  When `vars.CLAUDE_CODE_ACCOUNT_EMAIL` (or fallback `vars.CLAUDE_ACCOUNT_EMAIL` / `vars.CLAUDE_ACCOUNT`)
  is configured on the repository or organization,
  quota-exhaustion skip notices include `Account: \`$account\`` alongside the API message,
  making it clear which account reached its quota limit.
