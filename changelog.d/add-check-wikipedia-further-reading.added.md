- `check-wikipedia-further-reading`:
  add a diff-scoped composite action and reusable workflow that flags a Wikipedia
  citation (`@wikipedia_<key>`) or link in a list item of a Further reading
  section of `.qmd` and `.md` files, since Wikipedia pages are citations only
  and never belong in Further reading
  ([#1093](https://github.com/Morrison-Lab/gha/issues/1093)).
  A list item is in a reading context when its nearest preceding heading says
  further, additional or online reading (or going further, learn more), it sits
  in a `.reading` div, or its file name contains `further-reading` or
  `sec-reading` (a subfile, whose heading is in the parent chapter).
  Wikipedia citations in ordinary prose are never flagged.
  Like `check-new-line-breaks` it blocks by default (`fail: true`), scopes to
  added lines (a moved line is not new), skips rather than scanning the whole
  tree when there is no base to diff against, and has a `whole-tree` mode.
