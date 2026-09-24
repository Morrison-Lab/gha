- **Non-blocking quality checks now emit `::warning` annotations instead of `::error` annotations**
  when running in advisory mode (`fail: false`).
  Previously, `check-new-line-breaks`, companion markdown lint checks
  (`check_list_item_splices.mjs`, `check_table_splits.mjs`),
  and `check-equation-renders` printed `::error file=...` annotations even when configured
  with non-blocking failure settings,
  leaving passing jobs with misleading error annotations on PR diffs.
  Blocking mode (`fail: true`) continues emitting `::error` annotations and failing the job.
