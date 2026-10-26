- `check-visualization-figures`:
  add a diff-scoped, blocking composite action and reusable workflow that flags a
  div whose title matches `visuali[sz]` (visualize, visualizing, visualization)
  but that has no figure, when a pull request adds a line to it (Ezra, 2026-10-26).
  For an exercise, the figure may be in the exercise or in its solution,
  either a `#sol-<slug>` div in the same file or the sibling `_sol-` file.
  It counts figures as `check-exm-figures` does,
  and an `<!-- no-figure: reason -->` comment inside the div is the justified exception.
