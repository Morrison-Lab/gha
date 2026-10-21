- **`annotation-gate` allows `require-clean-verdict`'s non-clean verdict annotation** ([#1145](https://github.com/Morrison-Lab/gha/issues/1145)).
  `review / require-clean-verdict` already fails its own job when a review returns `needs-more-work`,
  so failing `annotation-gate` on `Claude review verdict is not clean (verdict: ...).` only duplicated the failure
  and left an uncleared `annotation-gate` check run on the commit whenever a subsequent review ran on the same SHA.
