- **`claude.yml` now tolerates extra whitespace in an `@claude review` request**
  (#315). The dispatch matcher previously did a literal substring check for a
  single space between `@claude` and `review` — a comment or review body with
  a double space (an easy typo, e.g. via autocomplete) silently failed to
  match, so the review was never dispatched and nothing told the requester why.
  A new `Detect @claude review request` step resolves a whitespace-tolerant
  match once (via a bash regex), and the two gated steps that previously
  repeated the fragile `contains(..., '@claude review')` check now reference
  that step's output. A third site, the late-arrival rescan, never used
  `contains()` — it independently regex-tests each fetched comment/review body
  via `jq`, so it keeps its own regex, updated with the same `\s+` treatment.
