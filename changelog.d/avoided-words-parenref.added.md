- `check-avoided-words` flags a trailing parenthetical link on a line a pull request adds:
  a crossref such as `differentiable at $c$ (@def-differentiable)` after a word,
  or a `([why](url))` link after a claim.
  Link the term itself, or make the whole claim the link text.
  This rule fails the run whatever `fail` says, while the other rules stay warn-only by default.
  `(see @thm-x)` passes ([gha#1402](https://github.com/Morrison-Lab/gha/issues/1402)).
