- **`antigravity-code-review` gains Vertex AI auth, diff limits, and a
  fail-closed error default** (#672).
  Workload Identity Federation via `workload-identity-provider` /
  `service-account`, routed to the SDK through the new `gcp-project` /
  `gcp-location` inputs --- all four are needed together, since the first two
  authenticate to GCP and the last two are what switch the SDK to Vertex.
  `max-diff-lines` / `max-diff-files` skip oversized diffs rather than
  spending on them.
  `fail-on-error` defaults to `true`, so a metadata, diff, or execution
  failure reddens the check instead of exiting 0 over a silent thread.
  A `safe-to-test` label lets a maintainer admit a fork PR after reading its
  diff; it must be re-applied per push.
