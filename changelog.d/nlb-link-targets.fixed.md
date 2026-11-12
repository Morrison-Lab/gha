- `check-new-line-breaks` now reads a link target the way Pandoc does (gha#1927).
  A destination may hold balanced parentheses or spaces, or sit in angle brackets,
  and a quoted title may hold a `)`, an escaped quote, or a nested quotation,
  so a dot, `!`, or `?` in `](https://x.org/A_(b. C))` or `](u "Fig. 1. The guide")` no longer ends a sentence.
  An angle destination needs no space before its title.
  A `;` anywhere in such a target is no longer a clause break,
  and the whole target is left out of the 80-character length gate.
  A `]` that closes no `[` is read as the end of link text wrapped from the line before,
  unless a `[` outside code, an HTML tag or comment, or math comes earlier on the line.
  Text that only looks like a link stays prose.
  That covers a `](` with no closing `)`, a title followed by more text,
  a `]` that closes a footnote reference, and a reference link such as `[x][r]` followed by `(...)`.
  It also covers a `](` inside a code span, an HTML tag, an HTML comment, or math.
