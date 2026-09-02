- **`claude-code-review`'s quota-skip PR notice names which quota case
  fired** (#804).
  The notice used to say "No secret is configured, or quota is exhausted" on
  every graceful skip, including a mid-run `429` where the credential had
  authenticated and the API's own message named the reset time.
  The guard now emits `quota_reason` (`missing-secret`, `rejected-at-door`,
  or `midrun-429`) and the captured API message next to `quota_exhausted`,
  the payload carries both, and a new `build-quota-skip-notice` composite
  renders per-case wording with the API message quoted verbatim.
