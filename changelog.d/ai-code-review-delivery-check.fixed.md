- `ai-code-review`: the candidate loop no longer accepts a dispatched run that
  finished without producing a verdict, closing two fail-open branches (#362).
  A run whose id could not be located within the poll window now falls through
  to the next candidate instead of exiting `0`.
  A poll that could not find its own run has learned nothing about whether the
  review happened, so that was the branch where the least was known.
  The run-location poll also takes the oldest run created at or after its own
  dispatch rather than the newest.
  `gh run list` returns newest-first, so a second dispatch landing inside the
  poll window handed back the wrong run.

- Ships the marker classifier the remaining hole needs, without wiring it in
  yet.
  `classify-review-delivery.sh` decides whether a dispatched review delivered a
  verdict, by looking for the agent's own no-verdict marker inside a PR comment
  naming that run.
  `ai-code-review.yml` cannot call it until `v2` advances past this merge, since
  a new composite action cannot gain its first `@v2` caller in the PR that
  introduces it (#569).
