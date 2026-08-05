- Add `report-failure.yml`, a reusable workflow that files an issue when a
  watched job fails, or comments on the issue already open for that failure
  instead of filing another. It is for workflows that run where no pull
  request carries their result -- a push to the default branch, a schedule, a
  release -- where a red run is otherwise visible only in the Actions tab.
  Add it as a final job gated on the job you want watched; see
  `examples/report-failure.yml`. It is a separate workflow rather than a job
  inside `quarto-publish.yml` because a reusable workflow's jobs can only hold
  permissions the caller granted, so folding it in would have made
  `issues: write` mandatory for every existing caller of that workflow
  ([#325](https://github.com/Morrison-Lab/gha/issues/325)).
