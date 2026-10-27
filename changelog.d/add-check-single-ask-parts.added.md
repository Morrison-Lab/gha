- `check-single-ask-parts`:
  add a diff-scoped composite action and reusable workflow
  that warns when a pull request adds or revises a part of an exercise div (`#exr-`),
  meaning a list item or paragraph outside its solution,
  that asks for more than one thing, such as "Compute X, and compare it with Y".
  Each exercise part asks for one thing (Ezra, 2026-10-27).
  `<!-- single-ask-ok: reason -->` exempts a part.
  Like `check-rubric-checklists` it warns by default, because the check is a heuristic,
  and it skips rather than scanning the whole tree when there is no base to diff against.
