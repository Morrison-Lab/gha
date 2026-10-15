- `check-informal-definitions`:
  flag a `::: {#def-...}` div that defines more than one term,
  meaning more than one distinct bold term
  that is not introduced as an alias
  ("also called", "or", "known as").
  Repeats of a term, bare abbreviations, symbols,
  glosses in parentheses or quotes, and bold inside a nested div
  are not counted.
  In diff-scoped mode a div is examined when any of its lines was added.
  Run over `Morrison-Lab/lds` it found 18 such divs.
  The report now says "definition problems",
  since a finding is no longer always a definition written in prose.
