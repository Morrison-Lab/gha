- **`check-new-line-breaks` now splits at a sentence that opens with a bare
  lowercase word** (#389).
  The splitter's lookahead required the next sentence to start with an uppercase
  letter or markup, so a line such as
  `it went red. renv restored the lockfile.`
  read as one sentence and shipped unflagged --- the shape our prose writes
  most, since it routinely opens a sentence with a lowercase package or repo
  name (`renv`, `serodynamics`).
  A second regex branch accepts a lowercase follower, guarded by a
  two-lowercase-letter lookbehind so a single-letter initial (`U.S.`), a dotted
  abbreviation (`a.m.`), a decimal or version (`v2.1`), and an ellipsis
  (`wait... foo`) are still left intact.
