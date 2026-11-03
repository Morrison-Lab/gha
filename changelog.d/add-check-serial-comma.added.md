- **`check-serial-comma`**, a diff-scoped check that fails when a PR adds a
  list of three or more items with no comma before the final "and" or "or".
  It joins each paragraph before matching, so a sentence split across lines by
  semantic line breaks is still checked, and it skips introductory phrases,
  code, math, comments, and tables.
  A line carrying `<!-- check-serial-comma: allow -->` is exempt.
  The rule is in the psw grammar chapter
  ([Morrison-Lab/psw](https://github.com/Morrison-Lab/psw)).
