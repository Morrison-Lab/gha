- **`classify-review-verdict.sh` reads a `review-data` payload's own
  `verdict` field before falling back to the prose scan** (#845). A review
  body carrying a well-formed `<!-- review-data: {...} -->` block (a
  `schema_version` key and a `verdict` of `CLEAN` or `NOT_CLEAN`) is now
  classified from that field directly, ahead of `strip_machine_payloads`
  discarding the block. Previously the classifier depended entirely on
  prose vocabulary it recognized, so a triage-exemption verdict like "No
  action -- ... does not need code review" scored `unrecognized` even
  though the same comment's payload already said `"verdict": "CLEAN"`
  (measured on sparta#1547). Independently, `clean_kw` now also recognizes
  `no action` and `does not need (code )?review` (contractions included),
  so a body without a payload still parses correctly.
