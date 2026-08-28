- `claude-code-review.yml`: a review run that produced no verdict after an
  executed background `Agent`/`Task` spawn (`run_in_background` absent or
  `true`, with no matching denial) is now classified with its own
  `failure_kind=background-agent` and excluded from the gha#185 same-prompt
  stub-retry, instead of being retried as a generic stub.
  The gha#392 failure shape has a poor retry recovery record
  (gha#536: 8 stub attempts, 2 recoveries),
  and each attempt bills real money.
  The posted review-failure comment names the mechanism
  and says the non-retry was deliberate.
  Detection keys on the structured `tool_use` field,
  confirmed against a real execution artifact,
  never on the final message's prose (#551).
