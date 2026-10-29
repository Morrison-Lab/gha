- `check-unexplained-contrasts`:
  add a diff-scoped, warn-only composite action and reusable workflow that flags a contrast
  ("X, not Y", "does not mean", "is not a", "rather than a") in a `#def-`, `#rem-` or `#note-` div that cites no source
  ([#1302](https://github.com/Morrison-Lab/gha/issues/1302)).
  A kept contrast must say who holds the other reading, with a source (psw: Do not rule out readings no reader would make).
  Whether anyone holds the other reading cannot be checked by a script, so the check prompts the author and does not block by default.
  A citation anywhere in the div clears it, and `<!-- check-unexplained-contrasts: allow -->` on a line exempts it.
  Like `check-def-commentary` it scopes to added lines and skips rather than scanning the whole tree without a base.
