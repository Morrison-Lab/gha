- **The `@claude review` matcher no longer fires on a mention inside a code
  span or a fenced code block** (gha#344).
  Backticks are the standard Markdown way to write "this is a literal string,
  not something I mean", so a comment *documenting* the accepted phrasings
  dispatched a review just by quoting them.
  That cost compounds: discussing the matcher spends a review run, and the
  dispatched review cancels whichever one was already in flight for that pull
  request.
  Code spans, fenced blocks, indented code blocks, and blockquotes are now all
  removed before matching, so quoting a request cites it rather than
  re-issuing it.
  The stripping follows CommonMark rather than approximating it: a span may
  contain a line break, a fence is capped at three spaces of indentation at
  both ends, and four columns after a blank line opens a code block.
- **The stripping moved into its own script,**
  `.github/workflows/scripts/strip-non-invoking-markup.sh`, with its own
  offline test table.
  Blockquote and CRLF handling moved there unchanged from
  `detect-review-request.sh`; the code-span and fence handling is new.
  A code span becomes a placeholder word rather than being deleted, because
  deleting it lets its neighbours close up into a request nobody wrote --
  "@claude `foo` review" would otherwise collapse into a dispatch.
