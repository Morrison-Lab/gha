- `check-visualization-figures`:
  add a diff-scoped, blocking composite action and reusable workflow that flags a
  div that asks for a picture but has no figure, when a pull request adds a line to it
  (Ezra, 2026-10-26).
  Every div whose title mentions visualization has a figure, and for an exercise the solution includes it.
  The trigger is wider than that word, so the rule's own example,
  "Mark every zero-gradient point on a surface", is caught:
  a visual word (plot, sketch, draw, diagram, contour, picture, or mark points on a surface)
  in an exercise or example title, `visuali[sz]` in any title,
  or a sketch or plot request in an exercise prompt.
  An exercise's figure may be in the exercise, its solution, or another file of its family.
  It counts figures as `check-exm-figures` does,
  and an `<!-- no-figure: reason -->` comment inside the div is the exception for a false positive.
