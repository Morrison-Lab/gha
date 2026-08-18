- **`claude-code-review.yml`'s reviewer can no longer call `ScheduleWakeup`,
  `SendMessage`, or `Monitor`, and is explicitly told not to delegate the
  review to a background agent or wait for external state** (#218,
  [anthropics/claude-code-action#1462](https://github.com/anthropics/claude-code-action/issues/1462)).
  The reviewer runs as a single synchronous CI job with no one to resume it
  afterward, so a run that spawns background work or schedules a follow-up
  "for later" never actually completes -- the process exits, killing any
  background subagent, and the run reports success with no `### Verdict`
  ever posted. `ScheduleWakeup`/`SendMessage`/`Monitor` are now denied
  outright (an upstream-confirmed failure signature, not just this repo's
  guess), on top of the existing "a denied tool call is never a reason to
  stop early" prompt guidance.
