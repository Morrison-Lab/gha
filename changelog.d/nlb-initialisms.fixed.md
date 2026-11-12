- `check-new-line-breaks` no longer splits a sentence after an uppercase dotted initialism
  that one of a few listed words follows, such as `the U.S. Supreme Court` (gha#1927).
  Only words that almost never open a sentence are listed,
  so `the U.S. Then it grew` and `the U.K. Court records show` still split.
