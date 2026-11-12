- `check-new-line-breaks` now reads a link target the way Pandoc does (gha#1927).
  A destination may hold balanced parentheses or spaces, or sit in angle brackets,
  and a quoted title may hold a `)` or an escaped quote,
  so a dot, `!`, or `?` in `](https://x.org/A_(b. C))` or `](u "Fig. 1. The guide")` no longer ends a sentence.
  A `;` anywhere in such a target is no longer a clause break,
  and the whole target is left out of the 80-character length gate.
  Text that only looks like a link stays prose.
  That covers a `](` with no closing `)`, a title followed by more text,
  and a `]` that closes no `[` or closes a footnote reference.
  It also covers a `](` inside a code span, an HTML tag, an HTML comment, or math.
