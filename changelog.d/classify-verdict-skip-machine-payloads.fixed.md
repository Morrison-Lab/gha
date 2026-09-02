- **`claude-code-review`'s verdict classifier ignores HTML comments and
  fenced blocks** (#819).
  The structured review-data payload sits after the verdict heading and the
  scan is last-match-wins, so one finding word in its JSON prose overrode the
  reviewer's stated verdict: on #811 the phrase "concurrency-deadlock audit"
  scored an approving review as `impasse`, and `require-clean-verdict` failed
  the job on it.
  Stripping happens before the heading is located, so a heading quoted inside
  a fence no longer wins either, and comment spans are excised rather than
  whole lines, so a verdict sharing its line with a comment survives.
  Every fenced block is ignored, not only the payload
  spellings this repo emits, which means a blocking note placed inside a
  fence is not read as one.
