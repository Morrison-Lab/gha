- `check-hybrid-sentences`:
  add a diff-scoped, warn-only composite action and reusable workflow
  that flags a hybrid sentence: one condition in words and another as a relation
  between math expressions, as in "The risk is zero if and only if $f = g$"
  (Ezra, 2026-10-29).
  A sentence is entirely in words or entirely in math, so the fix is two sentences,
  one in words and one displayed in math.
  `<!-- hybrid-ok: reason -->` exempts a paragraph.
  It warns by default, because the heuristic reads connectives ("if and only if",
  "and", "or") next to an inline relation,
  and checks only paragraphs that the pull request edits.
