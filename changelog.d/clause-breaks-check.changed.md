- **`check-new-line-breaks` now also flags a long line carrying a mid-line
  semicolon** (#336), on top of the sentence check it already ran.
  This is a proxy for the [SemBr spec](https://sembr.org)'s rule 5
  ("a semantic line break SHOULD occur after an independent clause"),
  alongside the rule 4 MUST the check already enforced.
  It is a proxy rather than a test of the rule, since deciding whether a mark
  ends an *independent* clause needs a parser.

  The new check is **on by default**, so existing callers get the extra
  annotations without changing anything.
  That is safe because the whole check stays warn-only unless `fail: true` is
  set: it adds annotations, not build failures.
  Set the new `clause-breaks: false` input to check sentences only, and
  `clause-min-length` (default `80`, the spec's own rule 12) to move the
  length gate.

  Of the four marks rule 5 names, only the semicolon is used, and only past
  that gate: see #336 for the
  hit rates behind that choice.
  The gate measures a line's visible length, after stripping inline markup
  such as code spans, link targets, bare URLs, and HTML entities, so a line
  that is long only because of a URL does not qualify -- rule 13's own
  exemption.
