- **A review that fails on an API 401 now says the credential was rejected**
  (gha#1005).
  An expired or revoked `CLAUDE_CODE_OAUTH_TOKEN` used to be reported as a
  generic `hard-error`, whose comment said "the cause lies elsewhere" and
  named no remedy, so one maintainer read it as a quota problem.
  `check-review-execution.sh` now maps the structured `api_error_status: 401`
  to a new `auth-rejected` kind.
  The failure comment names the secret, says this is not a quota limit, and
  gives the remedy: regenerate the token with `claude setup-token` and update
  the repository or organization secret.
  The check stays red, since a re-run fails the same way until the secret is
  replaced.
