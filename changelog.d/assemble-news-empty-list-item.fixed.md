- **`assemble-news` no longer mistakes an empty list item for a thematic
  break** (#741).
  Bullet-style detection skipped any candidate line that stripped to nothing
  once its marker and whitespace were removed, on the grounds that a spaced
  CommonMark thematic break (`- - -`) strips that way while a real bullet
  leaves content behind.
  A genuinely empty list item -- a line that is just `- `, a marker and a
  space with no content -- strips to empty too, so it was skipped as well and
  the file's style was taken from some later bullet instead of from its own
  first one.
  Detection now tests the CommonMark break shape directly: three or more of
  the same `-` or `*` marker with only whitespace between them.
  Fewer markers than that is a list, and a spaced run of `+` is a list at any
  length, `+` never being a thematic break marker.
