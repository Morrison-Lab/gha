- `preview` and the `quarto-publish` build job pick their runner from a `CI_RUNNER_HEAVY` variable when `runs-on` is empty and the repository is private, then fall back to `CI_RUNNER` and `ubuntu-latest`.
  With the variable unset nothing changes ([gha#1563](https://github.com/Morrison-Lab/gha/issues/1563)).
