- **`check-new-line-breaks` no longer splits a bold numbered label such as
  `**2. Used up.**` into two sentences** (gha#1001).
  The `**2.** text` form was already protected (gha#947), but a number that
  opens a longer emphasized label was read as a sentence end.
  Only the number's own dot is protected, so a sentence that follows the
  label is still flagged.
