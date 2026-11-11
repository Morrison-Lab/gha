- `check-term-links`:
  a code fence inside a blockquote (`> ` before the fence) is now skipped as code instead of read as prose, so a defined term in quoted code is no longer reported (gha#1905).
  Such a fence ends with its blockquote, as CommonMark says, so an unclosed one cannot hide the prose after the quote.
