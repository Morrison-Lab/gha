- **`check-equation-labels`**:
  add a composite action and reusable workflow, diff-scoped and blocking,
  that flags a `$$ ... $$` display equation with no `{#eq-...}` label,
  since only a labeled equation gets a number and an anchor.
  It moves the repo-local check from
  [Morrison-Lab/ids#201](https://github.com/Morrison-Lab/ids/pull/201),
  and adds diff scoping, a `whole-tree` mode, and an allow comment.
