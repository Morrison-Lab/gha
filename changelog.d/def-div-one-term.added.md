- `check-informal-definitions`:
  flag a `::: {#def-...}` div that defines more than one term,
  meaning more than one distinct bold term
  that is not introduced as an alias
  ("also called", "or", "known as").
  Repeats of a term (including its plural), bare abbreviations, symbols,
  glosses in parentheses or quotes, bold inside math, HTML comments or
  a nested div (matched by fence length) are not counted,
  and an alias cue may wrap onto the previous line.
  In diff-scoped mode a div is examined when any of its lines was added.
  Run over `Morrison-Lab/lds` it found 18 such divs.
  The report now says "definition problems",
  since a finding is no longer always a definition written in prose.
