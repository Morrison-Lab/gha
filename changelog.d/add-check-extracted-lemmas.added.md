- `check-extracted-lemmas`:
  add a diff-scoped, warn-only composite action and reusable workflow
  that flags a solution, example or proof stating a general fact
  ("for any", "for every" or "for all" with math)
  without citing a `#thm-`, `#lem-`, `#cor-` or `#prp-` result (Ezra, 2026-10-29, gha#1337).
  A theorem's own statement is not read,
  and `<!-- lemma-ok: reason -->` exempts a body.
  It warns by default, because the heuristic is unmeasured on other corpora,
  and checks only bodies that the pull request edits.
