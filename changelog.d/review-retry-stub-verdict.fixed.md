- **`claude-code-review.yml` now retries once when a review completes
  without an SDK error but never states a verdict** (#185). #187's fix (tell
  the reviewer up front that a denied tool call is never a reason to stop
  early) reduced but didn't eliminate the failure: a fresh reproduction after
  #187 was already merged and active still showed the same low-denial
  fingerprint (`is_error: false`, `permission_denials_count: 1`, no
  `### Verdict`), red-X'ing `require-review` for a PR that was never actually
  reviewed. `check-review-execution.sh`'s guard now surfaces this specific,
  retryable signature -- real non-empty assistant text, no SDK error, no
  verdict, AND a low `permission_denials_count` (<= 5 by default) -- as a
  `stub_review` output. The denial-count cutoff matters: it's what actually
  keeps this from also firing on #198's textually identical but
  much-higher-denial-count pattern (17-35 vs. #185's 1), which has
  repeatedly NOT recovered on retry per #198's own findings and would
  otherwise double an already-expensive ($2-4/attempt) failure mode. Also
  distinct from a hard SDK error or genuinely empty output, neither of which
  is retried. When it fires,
  `claude-code-review.yml` re-runs the same review prompt once, with an added
  instruction that this is a retry and must end with a verdict regardless of
  what gets denied along the way, before failing the check for real. The
  `anthropics/claude-code-action` call itself moved into a new
  `run-claude-review-attempt` composite action so the retry doesn't duplicate
  that ~100-line step. The raw execution output is also now uploaded as a
  workflow artifact on every attempt (`claude-review-execution-*`, via a new
  `upload-review-execution` composite action shared by both attempts), so any
  future recurrence has a downloadable turn-by-turn transcript to diagnose
  instead of needing `show-full-output` pre-enabled and a lucky re-trigger.
