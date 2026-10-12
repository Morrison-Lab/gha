- **`claude-code-review.yml`'s `require-clean-verdict` now fails, instead
  of skipping, when no review ran because the API quota was exhausted or
  the default-branch workflow restore failed.**
  GitHub counts a skipped required check as passing, so a quota skip let an
  unreviewed PR read as merge-clean (measured on Morrison-Lab/lds#454).
  `require-clean-verdict` attests that a clean verdict exists, and on those
  paths none does; re-run the review once quota is available.
  `require-review` keeps its gray skip there, since it attests delivery and
  the skip notice was delivered.
  The other gray skips (draft, fork, bot author, cancellation, stale head)
  are unchanged
  ([gha#1019](https://github.com/Morrison-Lab/gha/issues/1019)).
