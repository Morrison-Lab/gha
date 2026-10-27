- `check-rubric-checklists`:
  add a diff-scoped composite action and reusable workflow
  that warns when a pull request adds or revises a grading rubric
  (a line opening with `Grading`, `Rubric` or `Marking scheme`)
  whose block holds no task-list item (`- [ ] ...`).
  Most STEM grading rubrics are checklists (Ezra, 2026-10-27).
  Code fences and comments do not count;
  `<!-- rubric-ok: reason -->` exempts a rubric with no separable criteria.
  Like `check-multipart-exercises` it scopes to touched rubrics
  and skips rather than scanning the whole tree when there is no base to diff against.
  Unlike it, the check warns by default (`fail: true` blocks),
  because the rule is a default for most rubrics, not an absolute one.
