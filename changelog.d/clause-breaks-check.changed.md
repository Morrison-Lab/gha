- **`check-new-line-breaks` now also flags a long line that joins two
  independent clauses with a semicolon** (#336), on top of the sentence check
  it already ran.
  This is a narrow slice of the [SemBr spec](https://sembr.org)'s rule 5
  ("a semantic line break SHOULD occur after an independent clause"),
  alongside the rule 4 MUST the check already enforced.

  The new check is **on by default**, so existing callers get the extra
  annotations without changing anything.
  That is safe because the whole check stays warn-only unless `fail: true` is
  set: it adds annotations, not build failures.
  Set the new `clause-breaks: false` input to check sentences only, and
  `clause-min-length` (default `80`) to move the length gate.

  Only the semicolon is used, and only past a length gate, because a comma is
  overwhelmingly a list separator rather than a clause boundary and a colon
  usually introduces a list.
  Measured over a 22,820-line conformant corpus, keying on every mark the
  spec names flags 50.5% of already-conforming lines, against 0.7% for this
  check.
  The gate measures a line's visible length, so a line that is long only
  because of a link target or a code span does not qualify.
