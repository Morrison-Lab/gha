In `examples/claude-code-review.yml`, `examples/antigravity-code-review.yml`, and `.github/workflows/claude-review.yml`, add `pull-requests: read` permission to `dispatch-on-comment` jobs.
This prevents HTTP 404/403 API errors when reading PR metadata and file sets in private repositories with restrictive token permissions (gha#612).
