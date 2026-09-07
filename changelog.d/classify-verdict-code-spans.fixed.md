- **`classify-review-verdict` no longer scores the contents of inline code
  spans** (#827).
  `strip_emphasis` deleted the tick characters and classified the words inside,
  so a backticked identifier such as `` `NOT_CLEAN` `` became the two words
  "NOT CLEAN" and matched the negated-positive pattern as a rejection.
  Because the scan is last-match-wins over the lines after the verdict heading,
  one such line outranked an approving `**Ready for merge**` above it
  and failed `require-clean-verdict` on a clean review.
  Code spans are now blanked before classification,
  using CommonMark's own closing rule
  (a run of N backticks closes only on a run of exactly N),
  and an underscore between two alphanumerics is kept
  as part of the identifier rather than treated as emphasis.
  This is the inline-code sibling of #819's fenced-block exclusion,
  and it matters because the reviewer's own brief tells it
  to wrap quoted verdict words in backticks,
  so following that brief exactly is what produced the false negative.
