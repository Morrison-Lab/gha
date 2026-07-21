- **`claude-code-review`'s hallucination-watch prompt now tells the reviewer
  to `WebSearch`/`WebFetch` an unfamiliar external name before flagging it**
  (#277, #278). The prompt already grants `WebSearch`/`WebFetch` and tells the
  reviewer to fact-check claims and citations with them (#266), but the
  hallucination-watch paragraph itself only said to verify questionable
  symbols "against the codebase and its dependencies" — nothing pointed it at
  the search tools for an externally-referenced product, tool, service, or
  API name. That gap let the reviewer treat "I don't recognize this" (a
  training-cutoff artifact) as "this is fabricated" for a real but very new
  product a PR had already linked docs for, rather than checking first.
