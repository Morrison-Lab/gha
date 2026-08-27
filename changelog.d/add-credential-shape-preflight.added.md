- **`claude-code-review` now rejects a structurally unusable API credential
  before starting a review** (#686).
  The pre-flight check previously asked only whether `CLAUDE_CODE_OAUTH_TOKEN` /
  `ANTHROPIC_API_KEY` was non-empty,
  so a secret set to the wrong content --- a PEM key, a JSON file, a wrapped
  terminal copy --- started a run that the SDK rejected at the door.
  The result classified as `hard-error`,
  whose PR comment says the cause "lies elsewhere" and points at the run log,
  sending a triager to the diff when the cause is a repository secret only an
  admin can repair.
  A new `check-credential-shape` composite action decides this up front,
  and a new `bad-credential` failure kind names the affected secret and the
  remedy on the PR thread.
  The check flags only whitespace that survives trimming,
  so a trailing newline from `gh secret set < file` is still accepted.
