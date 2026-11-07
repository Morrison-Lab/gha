- **`quarto-publish` `incremental-cache` input**
  ([#1575](https://github.com/Morrison-Lab/gha/issues/1575)).
  After a successful render, it saves `_freeze`, the output directory and `.quarto`
  under the `quarto-incremental-` key that an incremental preview restores,
  so a pull request's first preview renders only the pages it changed.
  Off by default.
