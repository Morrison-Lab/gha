- **`claude-code-review`'s guard now names the denied tools, not just how many
  there were** (#540).
  When a review run ends without a verdict, `check-review-execution.sh` logs a
  per-tool breakdown (`Taskx6 Bashx3 WebFetchx2`) and one argument sample per
  tool beside the existing `permission_denials_count`, and repeats both in the
  over-threshold warning annotation so they are visible without opening the job
  log.
  The names were already in the execution result's `permission_denials` array;
  only the count was being surfaced, which left a red check reading as "the
  reviewer gave up" rather than as a permissions gap with a specific fix.
  Token-shaped literals in the sample are redacted.
  A result carrying a positive count but no array reports that the names are
  unavailable; one whose count could not be parsed at all reports that the
  count itself is unknown.
  Neither is described as a run with named denials.
  The summarizer's jq lookups are `?`-suppressed against a malformed denial
  entry (for example a string `tool_input`), which would otherwise abort the
  whole script before it classified the review at all.
