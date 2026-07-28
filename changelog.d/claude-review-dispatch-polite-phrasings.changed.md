- **`claude.yml` recognizes punctuated and polite `@claude review` requests**
  ([UCD-SERG/serodynamics#277](https://github.com/UCD-SERG/serodynamics/issues/277)).
  The dispatch matcher required whitespace and nothing else between `@claude`
  and `review`, so `@claude, please review` and `@claude can you review this?`
  never reached the review workflow -- the agent answered them itself instead,
  and consumers that noticed worked around it with a second, local dispatch
  job that then double-dispatched every plain `@claude review`.
  The matcher now also accepts punctuation and a closed set of polite lead-ins
  (`please`, `can/could/would/will you`, `kindly`, `pls`), and ignores quoted
  (`> `) lines so a quote-reply no longer re-dispatches a review.
  It deliberately still does not match arbitrary words between the mention and
  `review`: a
  false positive suppresses the agent's own reply, so `@claude the review
  workflow is broken, can you fix it?` must stay a question rather than become
  a review request.
- **The matcher moved into a tested script** shared by both dispatch paths.
  `claude.yml`'s trigger-comment check and its late-arrival rescan each carried
  their own copy of the pattern -- one in bash, one in `jq` -- which is how they
  came to disagree.
  Both now call `.github/actions/detect-review-request`, covered offline by
  `.github/workflows/scripts/tests/run-detect-review-request-tests.sh`.
