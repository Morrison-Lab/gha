- **`require-clean-verdict`'s fallback lookup matches the commit the run reviewed, not the live PR head.**
  Re-running an older run no longer goes green on a fallback review recorded for a newer head.
  A comment with several `Reviewed-Commit:` lines speaks for its last one only.
  A classifier failure on the newest matching comment reports no fallback, with a warning, instead of aborting the search
  ([gha#1229](https://github.com/Morrison-Lab/gha/issues/1229)).
