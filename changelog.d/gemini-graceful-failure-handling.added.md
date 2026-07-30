- **`gemini.yml` and `gemini-code-review.yml` now fail gracefully on a
  quota/auth/suspension error** (#379). A `run-gemini-cli` call rejected for
  quota exhaustion, an authentication failure, or a suspended project now
  posts a distinct `> [!WARNING]` comment via the new
  `.github/actions/report-gemini-failure` composite action
  (`classify-gemini-failure.sh`) and stops there -- deliberately never
  retried, since retrying against a suspended or rate-limited key wastes CI
  time and can look like continued automated abuse to Google. A genuine
  failure (anything else) still fails the check, now with a comment instead
  of only a raw stack trace in the run log.
  `gemini-code-review.yml` also gains a `require-review` gate job, mirroring
  `claude-code-review.yml`'s own: it shows gray (skipped), not red, on a
  quota/auth graceful skip. Consumers gating merges on this workflow should
  use `review / require-review` in branch protection, not `review / review`.
