- **Three real-world comment shapes pinned in `detect-review-request`'s test
  table** (#455).
  The matcher was verified against 20 comment bodies taken verbatim from a real
  PR thread (`UCD-SERG/serodynamics#230`) and was correct on all 20, but three
  of those shapes had no analogue in `run-detect-review-request-tests.sh`,
  whose header states its cases are "the contract, not a sample".
  Added: a mention separated by whitespace *before* the punctuation
  (`@claude , please review`), which is how the mention is typed in the wild
  and which pins the `[[:space:][:punct:]]+` separator class rather than a
  punctuation-then-space ordering; a review request detached from the mention
  by a paragraph break, filed alongside the two existing known false negatives
  because this one was written by someone who did want a review and did not get
  one; and the agent's own trailing attribution footer, the highest-frequency
  body in the wild carrying the token, where a regression would be a
  self-trigger loop rather than a stray run.
  These are characterization tests: they pass against `main` today and exist to
  make a future widening a deliberate decision.
  The separator case was mutation-checked in isolation: narrowing the class to
  `[[:punct:]]?[[:space:]]+` flips it to `false` while the sibling
  `@claude, please review` and `@claude, review` positives still pass, which is
  the isolation claim.
  Exactly one other case flips alongside it, `@ai-review` under
  `BOT_NAME='@ai'`, which leans on the same class for its hyphen separator.
  So the pin is not vacuous.
