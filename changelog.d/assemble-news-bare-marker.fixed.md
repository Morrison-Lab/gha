- `assemble-news`: a bare list marker (`-`, `*` or `+` alone on a line) is
  now recognized as CommonMark's empty list item, both when detecting the
  consumer file's bullet style and when normalizing an inserted fragment's
  markers.
  Previously each required whitespace after the marker, so an empty item
  counted only when it carried a trailing space -- meaning the assembled
  file's marker style could flip on an invisible character that any
  whitespace-trimming editor removes ([#746](https://github.com/Morrison-Lab/gha/issues/746)).
