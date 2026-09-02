- **`claude-code-review`'s quota-skip PR notice names which quota case
  fired** (#804).
  The notice used to say "No secret is configured, or quota is exhausted" on
  every graceful skip, including a mid-run `429` where the credential had
  authenticated and the API's own message named the reset time.
  The guard now emits `quota_reason` (`rejected-at-door` or `midrun-429`)
  and the API message, redacted with the same chain `denied_tools` uses,
  beside `quota_exhausted`, and the pre-flight step emits `missing-secret`;
  `run-review-guard` exposes both, the payload carries them, and a new
  `build-quota-skip-notice` composite renders per-case wording with the
  message quoted inside the blockquote.
