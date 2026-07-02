- **Fixture-based test coverage for `claude-code-review`'s fail-check guard
  logic** (#174). The stub/placeholder-review detection added in #172 (and
  refined in #173) had no automated coverage — it was verified only by manual
  trace against known stub texts, since the guard runs after a live Claude API
  call that CI can't reproduce. The guard logic is now extracted into a
  standalone script (`.github/workflows/scripts/check-review-execution.sh`),
  and a new `review-fail-check` selftest job feeds it ten canned
  execution-output fixtures — a genuine finished review, each known stub
  variant (`Lacaedemon/sparta#590` and PR #171's two stub comments),
  empty/whitespace review text, an `is_error:true` result, a
  quota-exhaustion result, a `Verdict:`-label (non-heading) review, and a
  review whose verdict-bearing block isn't the last assistant block — and
  asserts each behaves as expected (pass / fail / graceful skip).
