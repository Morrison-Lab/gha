- `preview-deploy.yml` now cancels a PR's older preview deploy, queued or running,
  when a newer head's deploy starts,
  through a top-level `concurrency:` group keyed on the PR number
  (head repository and branch for a fork PR) with `cancel-in-progress: true`
  ([gha#1827](https://github.com/Morrison-Lab/gha/issues/1827)).
  The deploy job's `gh-pages` group still serializes deploys across PRs and the main-site publish.
  A caller must not name its own concurrency group with the `preview-deploy-` prefix.
