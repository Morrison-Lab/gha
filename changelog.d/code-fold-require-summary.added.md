- `check-code-fold` gains an opt-in `require-summary` input.
  With `require-summary: true`, it also flags a new executed chunk
  whose code folds but that sets no `code-summary`,
  so the toggle says what the hidden code does (Morrison-Lab/lds#2849).
  `default-fold: true` treats a chunk with no `code-fold` option as folded,
  for a project whose own `code-fold` default is true.
