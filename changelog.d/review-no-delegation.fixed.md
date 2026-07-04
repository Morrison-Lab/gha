- **`claude-code-review.yml`'s reviewer is now explicitly told not to delegate
  the review to a background agent, schedule a follow-up, or wait for
  external state** (#218). The reviewer runs as a single synchronous CI job
  with no one to resume it afterward, so a run that spawns background work
  and defers finishing the review to "later" never actually completes —
  producing a stub review (no `### Verdict` posted) that then fails
  `require-review`. The system prompt now says so explicitly, alongside the
  existing "a denied tool call is never a reason to stop early" guidance.
