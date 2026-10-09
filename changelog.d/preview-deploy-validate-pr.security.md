- **`preview-deploy` now checks the PR number in the preview artifact before using it.**
  The build half runs a fork PR's own workflow file, so a fork could upload an
  artifact naming any PR number, overwrite or remove another PR's preview, or
  name a path outside `pr-preview/`.
  The deploy job now accepts the number only if it is digits and that PR's head
  is the repository and branch the triggering run built, and the action only if
  it is `deploy` or `remove`.
  Found in review of [Morrison-Lab/wai#273](https://github.com/Morrison-Lab/wai/pull/273),
  whose own deploy workflow had this check.
