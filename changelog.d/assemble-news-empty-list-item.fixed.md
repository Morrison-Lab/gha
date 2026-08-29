- **`assemble-news` no longer mistakes an empty list item for a thematic
  break** (#741).
  Bullet-style detection skipped any candidate line that stripped to nothing
  once its marker and whitespace were removed, on the grounds that a spaced
  CommonMark thematic break (`- - -`) strips that way while a real bullet
  leaves content behind.
  A genuinely empty list item -- a line holding a `-` and the space after it,
  with no content of its own -- strips to empty too.
  So it was skipped alongside real breaks, and the file's style was taken from
  some later bullet rather than from its own first one.
  Detection now tests the CommonMark break shape directly: three or more of
  the same `-` or `*` marker with only whitespace between them.
  Fewer markers than that is a list, and a spaced run of `+` is a list at any
  length, `+` never being a thematic break marker.
