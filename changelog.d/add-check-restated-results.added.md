- `check-restated-results`:
  add a diff-scoped, warn-only composite action and reusable workflow
  that flags a derivation solution whose result no `#thm-`, `#lem-`, `#cor-` or `#prp-` div restates
  after the exercise (Ezra, 2026-10-29).
  A derivation is a `#sol-` whose exercise asks to derive, prove, show or solve without citing a stated result,
  and whose solution displays an equation.
  It follows `{{< include >}}` lines so the theorem may sit in a later subfile,
  and `<!-- restated-ok: reason -->` exempts a solution.
  It warns by default, because the heuristic is unmeasured on other corpora,
  and checks only solutions that the pull request edits.
