- **`claude-code-review.yml` now retries read-only GitHub API lookups in the reviewer stash and restore steps** (#261).
  Transient GitHub API errors or HTML 503 responses during the initial head SHA and requested-reviewers lookups previously caused immediate step failures under `bash -e`, burning a review round before any agent attempt could execute.
  Both the stash and restore steps now retry their read-only `gh api` calls up to 3 times with short backoffs and validation checks before failing.
