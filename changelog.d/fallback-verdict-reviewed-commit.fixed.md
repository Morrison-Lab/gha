- **`require-clean-verdict`'s fallback lookup matches the commit the run reviewed, not the live PR head.**
  Re-running an older run no longer goes green on a fallback review recorded for a newer head.
  A classifier failure on the newest matching comment now reports no fallback, with a warning, instead of skipping to an older review that the newest one may withdraw
  ([gha#1229](https://github.com/Morrison-Lab/gha/issues/1229)).
