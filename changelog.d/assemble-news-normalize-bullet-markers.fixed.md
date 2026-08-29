- **`assemble-news` normalizes fragment bullet markers on insertion** (#727).
  markdownlint's MD004 default (`style: consistent`) derives its required
  bullet marker from the assembled file's first bullet, so a fragment
  authored with a different marker than `NEWS.md`'s dominant one used to flip
  that requirement for the whole file.
  Every inserted bullet's top-of-line marker is now normalized to one
  target: the new `bullet-style` input when set, otherwise `news-file`'s own
  first existing bullet, otherwise `-` when the file has no bullet yet to
  take a style from.
  A CommonMark thematic break does not count as that first bullet (#727), and
  an empty list item does (#741) -- both match "a marker followed by a
  space", so the two are separated by the marker count a break requires.
