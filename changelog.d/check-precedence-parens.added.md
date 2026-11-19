- **`check-precedence-parens`**
  (Ezra's rule of 2026-11-19 that math uses parentheses
  to make operator precedence explicit):
  add a diff-scoped composite action and reusable workflow
  that fails a pull request adding math such as
  `\set{x : x \in A \lor x \in B}`,
  where a relation sits unparenthesized beside a logical connective,
  or `P \land Q \lor R`, where two kinds of connective share a level.
  Only lines a PR adds count, so existing pages never block.
  `check-common/mdmask.py` gains `math_spans`,
  moved from `check-macro-expansions`, which both checks now use.
