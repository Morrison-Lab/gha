- `check-exercise-ends-with-task`:
  add a diff-scoped composite action, and a reusable workflow,
  that fails a PR adding or editing an exercise (`#exr-` div) whose last paragraph holds no question or instruction,
  or that ends with a figure, table, code block, or include after its last task
  (Ezra, 2026-11-09, [psw#549](https://github.com/Morrison-Lab/psw/issues/549), [gha#1788](https://github.com/Morrison-Lab/gha/issues/1788)).
  Task sentences use the same test as `check-exercise-question-paragraph`, which the script imports.
  Solutions, hints, comments, display math, lists, and headings are not examined,
  and `<!-- ends-with-task-ok: reason -->` exempts an exercise.
  `fail: false` gives warnings only, and `whole-tree` measures a corpus.
