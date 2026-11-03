- **`check-serial-comma`** takes a `paths-ignore` input, so a repository can skip
  vendored content such as `_extensions/**` and `latex-macros/**`, as the sibling
  checks do.
  It matters most for a whole-tree run, which would otherwise scan files the
  repository cannot fix.
