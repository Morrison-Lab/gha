- `check-div-ids`:
  add a diff-scoped, warn-only composite action and reusable workflow that flags a fenced div
  with a theorem-type class (`.remark`, `.definition`, `.theorem`, ...) but no id with the matching prefix
  (`#rem-`, `#def-`, `#thm-`, ...) when a pull request adds its opening line.
  Without the id the div renders as a plain block quote, with no callout or number
  (Morrison-Lab/lds#1600, a private repository the link checker cannot reach).
  Existing divs are never reflagged.
