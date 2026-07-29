- **The `@claude review` matcher no longer swallows requests that ask for
  something to be reviewed *and* acted on** (gha#346).
  Widening the matcher to accept polite lead-ins also made
  `@claude can you review this and fix the failing test?` a review dispatch,
  which suppresses the agent's own reply -- so the question went to a
  read-only reviewer and nobody answered it.
  The keyword may now take an object, but only one pointing back at the pull
  request (`review this`, `review the latest changes`, `review again`), and
  the request has to end its line.
  Phrasings that name something to go look at are treated as ordinary agent
  requests again.
  The trade is deliberate: a pure review request whose object is not on the
  list -- `@claude review the changes I just pushed` -- now gets a
  self-review rather than a dispatched one, which is the cheaper of the two
  errors.
  Both known cases are pinned in the test suite.
- **CRLF comment bodies are normalized portably.**
  GitHub delivers bodies with CRLF line endings, and the matcher now anchors
  on a bare newline.
  The previous `sed 's/\r$//'` only worked under GNU sed -- BSD/macOS sed
  reads `\r` as a literal `r` -- and `runs-on` is a consumer-settable input.
- **`detect-review-request` probes for `base64 -d` vs `-D`** rather than
  assuming GNU coreutils, so decoding the late-comment scan's bodies does not
  fail the whole job on a non-GNU runner.
- **A late-comment scan that cannot be read no longer fails the run.**
  The collecting step already degraded a transient `gh api` error to "no late
  review"; the detection step now makes the same trade instead of contradicting
  it, and logs its result either way.
