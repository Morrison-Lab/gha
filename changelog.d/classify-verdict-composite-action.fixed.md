- **`claude-code-review.yml`'s verdict classifier now runs as a bundled
  composite action** (#812).
  The `Classify review verdict` step added in #790 was a bare `run:` of a
  repo-relative script, but a reusable workflow's `run:` step executes in
  the consumer job's checkout, where this repository's script tree does
  not exist -- so the step exited 127 in every consumer repository,
  failing `post-review`, `require-review`, and `require-clean-verdict`
  over an already-posted clean verdict.
