- **`check-new-line-breaks` now splits at a sentence that opens with a bare
  lowercase word** (#389).
  The splitter's lookahead required the next sentence to start with an uppercase
  letter or markup, so a line such as
  `it went red. renv restored the lockfile.`
  read as one sentence and shipped unflagged --- the shape our prose writes
  most, since it routinely opens a sentence with a lowercase package or repo
  name (`renv`, `serodynamics`).
  A second regex branch accepts a lowercase follower under two guards: a
  two-lowercase-letter lookbehind that refuses a single-letter initial (`U.S.`),
  a dotted abbreviation (`a.m.`), and an ellipsis (`wait... foo`); and a
  no-closing-class requirement that the terminal punctuation be immediately
  followed by whitespace, which leaves a quoted or parenthesized fragment
  (`he said "stop." then`) and mid-sentence emphasis (`**critical.** yet`) on
  one line.
  Lowercase abbreviation forms (`sec.`, `ms.`) are protected only on this new
  branch, in a second pass after the uppercase branch runs, so a lowercase unit
  before a lowercase word (`3 sec. then`) is left intact while the same unit
  before an uppercase word (`300 ms. The next ...`) still splits as the genuine
  sentence boundary it is.
