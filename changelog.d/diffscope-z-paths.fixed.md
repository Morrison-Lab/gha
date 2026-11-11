- The checks that use `check-common/diffscope.py` no longer skip a file whose name holds `"`, a backslash, or a tab (gha#1923).
  They list files through the new `diffscope.git_paths`, which runs `git ls-files` or `git diff --name-only` with `-z`,
  so the name arrives unquoted.
  This covers whole-tree runs of all thirteen such checks,
  and the diff modes of `check-one-div-per-subfile` and `check-heading-levels`.
