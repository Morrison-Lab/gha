- `annotation-gate-run`: a manual `workflow_dispatch` gate now has its own concurrency group.
  Before, it shared one with the `workflow_run` gates on the same commit.
  A newer `workflow_run` gate replaced the pending dispatch gate, so the dispatch never posted its check run (gha#1765).
