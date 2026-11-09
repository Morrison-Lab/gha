- `check-pr-size` does not count a pure rename toward the file cap,
  and exempts a PR whose description says "mechanical, content-identical"
  ([ai-config#5129](https://github.com/Morrison-Lab/ai-config/pull/5129),
  [gha#1734](https://github.com/Morrison-Lab/gha/issues/1734)).
  The caps stay at 10 files and 300 lines for content PRs.
