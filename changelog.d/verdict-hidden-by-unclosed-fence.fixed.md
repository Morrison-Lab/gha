- **`require-clean-verdict` no longer fails an approving review because a
  quoted diff left a code fence open** (gha#1021).
  A diff context line holding a fence (a space, then three backticks)
  closes a three-backtick `diff` block early.
  The diff's own closing line then opens a fence that hides the verdict and
  the review-data payload, so the review classified as `no-verdict`
  (Morrison-Lab/mds#194).
  When no verdict is found, `classify-review-verdict.sh` now blanks that
  stray opener and classifies the review again, with every existing check
  applied.
  A clean result from that second pass counts only when the payload names
  the full head commit, so a payload quoted from an earlier commit is still
  ignored, and an empty head SHA trusts nothing.
  The review brief also tells the reviewer to quote fenced content inside a
  four-backtick fence.
