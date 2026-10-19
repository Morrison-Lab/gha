- **`check-fform-paren`**
  ([#1112](https://github.com/Morrison-Lab/gha/issues/1112)):
  suggest `\namef{...}` only when `\namef` wraps its argument
  in the same delimiter the flagged text uses,
  read from the f form's definition (following `\def` aliases).
  Before, `\log\abs{x}` was suggested as `\logf{x}` although `\logf` builds in `\cb`.
