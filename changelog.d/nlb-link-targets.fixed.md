- `check-new-line-breaks` now reads a link target much as Pandoc does (gha#1927).
  A destination may hold balanced parentheses or spaces, or sit in angle brackets,
  and a quoted title may hold a `)`, an escaped quote, or a nested quotation,
  so a dot, `!`, or `?` in `](https://x.org/A_(b. C))` or `](u "Fig. 1. The guide")` no longer ends a sentence.
  An angle destination needs no space before its title,
  and a `<` with no `>` to close it is ordinary destination text.
  A `;` anywhere in such a target is no longer a clause break,
  and the whole target is left out of the 80-character length gate.
  A `]` that closes no `[` is read as the end of link text wrapped from the line before.
  An earlier `[` on the line cancels that reading when it sits outside code, HTML, and math.
  This is where the check departs from Pandoc on purpose,
  since Pandoc reads the whole paragraph and the check reads one line.
  Text that only looks like a link stays prose.
  That covers a `](` with no closing `)`, a title followed by more text,
  a footnote reference such as `[^1]`, and a reference link such as `[x][r]` followed by `(...)`.
  It also covers a `](` inside a code span, an HTML tag, an HTML comment, or math.
- Code spans are now removed in one linear pass, so a line of thousands of backticks no longer stalls the check.
  A backtick run with no closing run of its own length stays literal text, as in CommonMark.
