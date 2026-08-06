- **`check-new-line-breaks` now splits at a sentence that opens with a bare
  lowercase word** (#389).
  The splitter's lookahead required the next sentence to start with an uppercase
  letter or markup, so a line such as
  `it went red. renv restored the lockfile.`
  read as one sentence and shipped unflagged --- the shape our prose writes
  most, since it routinely opens a sentence with a lowercase package or repo
  name (`renv`, `serodynamics`).
  A second regex branch accepts a lowercase follower under two guards: a
  two-lowercase-letter lookbehind that refuses a single-letter initial (`U.S.`)
  or a dotted abbreviation (`a.m.`), and a no-closing-class requirement that the
  terminal punctuation be immediately followed by whitespace, which leaves a
  quoted or parenthesized fragment (`he said "stop." then`), mid-sentence
  emphasis (`**critical.** yet`), and an ellipsis (`wait... foo`) on one line.
  The abbreviation list now protects each entry in its conventional and
  lowercase forms (so a lowercase `sec.` is caught) but not its all-caps form,
  and keeps `No` case-sensitive so `No.` (number) stays protected while a
  lowercase `no.` (the word) still splits.
