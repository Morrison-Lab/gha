- **Retry and diagnose action short-circuit failures in `claude-code-review.yml`** ([#368](https://github.com/Morrison-Lab/gha/issues/368)).
  Detects missing execution files or missing result objects as action short-circuits (`action_short_circuit=true`), allowing same-run retry eligibility and explicit diagnostic error attribution instead of generic failure logging.
