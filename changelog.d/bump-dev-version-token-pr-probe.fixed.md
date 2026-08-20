- **`bump-dev-version` probes `WORKFLOW_TOKEN` pull-request access** (#524).
  The pre-flight guard added in #409 only checked that the secret was
  non-empty; a fine-grained PAT with Contents write but no Pull requests
  permission passed that check and then failed after the bump was already
  force-pushed.
  The reusable workflow now calls `gh api` on the repo's pulls
  endpoint before checkout when the secret is set, and fails fast with a
  message naming the permission gap.
