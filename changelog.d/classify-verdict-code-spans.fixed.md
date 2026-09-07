- **`classify-review-verdict` no longer flips a clean review to
  needs-more-work on quoted identifiers or on the word "already"** (#827).
  Two independent root causes produced the same symptom.
  `strip_emphasis` deleted the tick characters and classified the words inside,
  so a backticked identifier such as `` `NOT_CLEAN` `` became the two words
  "NOT CLEAN" and matched the negated-positive pattern as a rejection.
  Separately, `positive_targets` carried no leading word boundary,
  so the regex backtracked inside a word
  and "already" supplied a "ready" target to any preceding negator.
  Because the scan is last-match-wins over the lines after the verdict heading,
  either one outranked an approving `**Ready for merge**` above it
  and failed `require-clean-verdict` on a clean review.
  Code spans are now blanked before classification,
  confined to a single block and closed by CommonMark's own rule
  (a run of N backticks closes only on a run of exactly N),
  an underscore between two alphanumerics is kept as part of the identifier,
  and the positive targets are anchored on a word boundary.
