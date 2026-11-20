- **`check-ball-neighborhoods`**
  ([#2156](https://github.com/Morrison-Lab/gha/issues/2156), from
  [psw#684](https://github.com/Morrison-Lab/psw/issues/684)):
  add a diff-scoped composite action and reusable workflow
  that fails a pull request that adds a neighborhood written as a norm inequality,
  such as `\norm{\vx - \vx^*} < \delta` or `\abs{x - c} < \delta`,
  and suggests membership in a ball, `\vx \in \ball{\vx^*}{\delta}`.
  A norm with no difference inside, a comparison of two distances,
  and a difference whose first operand is a number pass.
  Only lines a PR adds count, so existing pages never block.
