- `check-split-solutions`:
  add a diff-scoped composite action and reusable workflow
  that fails a pull request touching a split exercise whose solution was not split with it
  ([#1290](https://github.com/Morrison-Lab/gha/issues/1290)).
  A split group is the `#exr-` divs sharing a slug once `-partK` is removed.
  It flags an exercise with no `#sol-` of its slug, an orphaned `#sol-`,
  a solution with lettered part labels or a "Part 2:" line,
  and a solution holding a figure that only a sibling exercise asks for.
  `<!-- split-solutions-ok: reason -->` exempts a solution.
  Like `check-multipart-exercises` it fails by default and skips without a base to diff against.
