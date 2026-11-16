- `check-title-references`:
  add a diff-scoped, failing-by-default composite action and reusable workflow that flags a link
  whose text is the title of the heading or page it targets, with no content type (section, chapter, page, ...)
  beside it, on a line a pull request adds (psw#660, gha#2046).
  Write "the [Title](#id) section", not "[Title](#id)".
  Books, articles and videos, whose titles live off-site, are left to the psw reviewer instruction.
  Like `check-avoided-words` it loads `check-write-idiom`'s engine, so it scopes to added lines,
  skips rather than scanning the whole tree when there is no base to diff against,
  and has a `whole-tree` mode.
