- **`classify-review-verdict` no longer treats a scope disclaimer as a rejection** (#849).
  When a review clarifies scope with explanatory prose such as
  "it is not a claim that the PR is fully clean end-to-end",
  `pos_gap_pattern` previously bridged from "not" across arbitrary words
  to match "clean" as a negated-positive rejection,
  overriding an approving `**Ready for merge**` verdict.
  Disclaimer phrases (such as "not a claim that...", "not claiming that...",
  "not a guarantee that...") now break the gap pattern,
  and positive targets within disclaimer clauses are masked
  so scope qualifications neither reject the review
  nor displace the stated verdict.
