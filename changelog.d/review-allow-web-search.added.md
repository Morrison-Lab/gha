- **`claude-code-review`'s reviewer gains full `WebSearch` access for
  fact-checking** (#266). The review guidelines ask the reviewer to verify
  prose claims, citations/DOIs/URLs, and code/math against external sources,
  but the fetch tools granted in #202 (`WebFetch`, `Bash(curl:*)`) only
  retrieve a URL the reviewer already has — search is what locates the
  authoritative source in the first place. The reviewer's system prompt is
  updated in lockstep to name the search tool as available. No new egress
  capability: the already-granted `Bash(python3:*)`/`Bash(curl:*)` permit
  arbitrary direct requests, and `WebSearch` queries are served through the
  Anthropic API rather than the runner's own network (#240 tracks the
  standing egress tradeoff). Also rewords the three stale "no network-fetch
  tools" claims (in `check-latex-macros`'s input description, its prompt
  block, and the reference page) left behind by #202's fetch-tool grant —
  the macro checks stay local-checkout-only, now justified by the pinned
  submodule version being authoritative rather than by a tool gap that no
  longer exists.
