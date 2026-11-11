- `claude-code-review.yml`'s incremental-range step now fails closed when the review history is unknown (gha#1032).
  A failed fetch of the PR's comments, and earlier bot verdict comments that name no usable `Reviewed commit:` boundary, each write an unreviewed-commit count of 1 and ask for a full-diff review.
  Before, both read as a first round and left the count at 0, so a "no new content" claim passed the gha#965 guard.
