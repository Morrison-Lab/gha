- `check-redundant-citations`:
  add a diff-scoped composite action and reusable workflow that flags a source
  cited twice, with the same locator or none, in one div or passage of `.qmd`
  and `.md` files, since a source is cited once per div, at the claim it
  supports ([#1105](https://github.com/Morrison-Lab/gha/issues/1105)).
  A div or passage runs between two `:::` lines or slide breaks.
  Every key in a bracketed citation counts, and so does every `@key` on a
  `Source:` line.
  In-text citations, repeats with a different locator, repeats in different
  list items, cross-references, code fences and chunk options are never
  flagged.
  Like `check-literal-math-letters` it is warn-only by default (`fail: false`),
  scopes to added lines (a moved line is not new), skips rather than scanning
  the whole tree when there is no base to diff against, and has a `whole-tree`
  mode.
