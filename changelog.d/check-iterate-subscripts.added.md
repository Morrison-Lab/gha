- **`check-iterate-subscripts`**
  (Morrison-Lab/lds#2435, a private repository):
  add a diff-scoped composite action and reusable workflow
  that fails a pull request that adds an iterate written with a subscript,
  such as `\vcoef_t` or `\vcoef_{t+1}`,
  and suggests `\iterpoint{\vcoef}{t+1}`.
  The `symbols` input names the macros (default `vcoef steplen`)
  and `indices` names the index letters (default `t \iter`).
  A number index such as `\vcoef_0` and a letter not listed pass.
  Only lines a PR adds count, so existing pages never block.
