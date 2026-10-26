- `check-def-commentary`:
  add a diff-scoped, blocking composite action and reusable workflow that flags commentary written inside a
  `#def-` div, a sentence opening "It is not", "This is not", "Note that", "Unlike", "Do not confuse" and similar
  ([#1180](https://github.com/Morrison-Lab/gha/issues/1180)).
  A definition holds the definition, its notation and its display equation only;
  commentary goes in a `#rem-` div right after it.
  Like `check-one-div-per-subfile` it scopes to added lines and skips rather than scanning the whole tree without a base,
  and `<!-- check-def-commentary: allow -->` on a line exempts it.
  Code fences, display math, HTML comments, inline code and nested non-definition divs are not read.
