- **`claude-code-review.yml` no longer passes a "no new content" verdict
  after a force-push.**
  When the previously reviewed commit is not an ancestor of the new head
  (orphaned by a force-push or rebase, or beyond the fetch limit),
  `compute-incremental-range.sh` used to emit nothing and leave the
  unreviewed-commit count at 0.
  That disabled the gha#965 guard, so a round claiming nothing had changed
  could pass `require-clean-verdict` over commits nobody reviewed.
  The script now fails closed: it tells the reviewer the previous boundary
  is gone and to review the PR's full diff, and it writes a count of 1, so
  a no-diff claim in that round is classified `unreviewed-commits-skipped`
  ([gha#1010](https://github.com/Morrison-Lab/gha/issues/1010)).
