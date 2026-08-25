- **Remove redundant top-level `concurrency` from `quarto-publish` caller stubs**
  ([#662](https://github.com/Morrison-Lab/gha/issues/662)).
  Because `quarto-publish.yml`'s `deploy` job now directly declares
  `concurrency: group: gh-pages`, callers declaring `concurrency: group: gh-pages`
  at the workflow level caused the nested deploy job to fail.
  Removing top-level concurrency from the caller stubs permits the build job to
  run without acquiring the `gh-pages` lock and allows the deploy job to serialize
  cleanly.
