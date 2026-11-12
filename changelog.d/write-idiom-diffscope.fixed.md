- `check-write-idiom`, and the checks that load it as their engine, now take their git calls and diff parsing from `check-common/diffscope.py` (gha#1856).
  A whole-tree run now lists files with `-z`, so a page whose name holds a quote, a backslash or a tab is scanned instead of skipped.
