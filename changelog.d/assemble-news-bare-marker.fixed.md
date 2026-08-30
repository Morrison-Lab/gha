- `assemble-news`: a bare list marker (`-`, `*` or `+` alone on a line) is now
  recognized as CommonMark's empty list item where it genuinely is one -- at
  the start of the file, after a blank line, or directly after another list
  item.
  Both the bullet-style detection and the fragment normalizer previously
  required whitespace after the marker, so an empty item counted only when it
  carried a trailing space, and the assembled file's marker style could flip
  on an invisible character that any whitespace-trimming editor removes
  ([#746](https://github.com/Morrison-Lab/gha/issues/746)).
  A bare marker under a paragraph line is left alone, since there it is a
  setext heading underline or paragraph text rather than a list item.
