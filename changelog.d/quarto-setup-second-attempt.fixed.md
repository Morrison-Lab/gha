- `preview`, `quarto-publish`, `lint-changed-lines`, `lint-changed-files` and `student-qmd`: when the `quarto-dev/quarto-actions/setup` step fails, the composite waits 90 seconds and runs it once more.
  The action's own download retries (20 in the failed run on macros#364) all got `504` and gave up, so one bad window failed the whole job (gha#1667).
  The first attempt no longer fails the job on its own, and the second attempt does.
