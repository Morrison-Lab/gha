- **`check-links` no longer fails a PR on a 5xx from a link the PR does not add** (#1052).
  A brief github.com outage returned `503` for blob links in files no PR touched,
  and `max_retries` did not help, so every PR in every consumer went red.
  The composite now reads lychee's JSON report and reports a 5xx as a warning annotation
  unless the link is on a line added since the new `base-ref` input's merge base with `HEAD`.
  `base-ref: all` keeps the old behaviour of failing on every 5xx.
  The `check-links.yml` reusable workflow passes `HEAD^1` on `pull_request`
  and gains a `fail-on-any-5xx` input that passes `all`.
  A 404, a network error, a timeout, and a lychee tool error still fail the check on any line,
  and a run that reports failures but lists none in its JSON report fails rather than passing.
  The `check-quarto-*` composites call `check-links` without a `base-ref`,
  so there every 5xx is now a warning.
