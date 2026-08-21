- **`claude-code-review`'s guard now names the denied tools, not just how many
  there were** (#540). When a review run ends without a verdict,
  `check-review-execution.sh` logs a per-tool breakdown (`Taskx6 Bashx3
  WebFetchx2`) and one argument sample per tool beside the existing
  `permission_denials_count`, and repeats it in the over-threshold warning
  annotation so it is visible without opening the job log. The names were
  already in the execution result's `permission_denials` array; only the count
  was being surfaced, which left a red check reading as "the reviewer gave up"
  rather than as a permissions gap with a specific fix. Token-shaped literals
  in the sample are redacted, and a result carrying a count but no array says
  so explicitly instead of printing an empty list.
