- `claude-code-review.yml`: the incremental range now leaves out commits already on the default branch even when the PR is stacked on another branch.
  A stacked PR merges `main` through its base, and the review read `main`'s files as scope creep (gha#1802, Morrison-Lab/lds#2196).
  The PR's own base is still never excluded.
