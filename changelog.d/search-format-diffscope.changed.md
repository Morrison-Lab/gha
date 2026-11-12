- `check-search-shortcut` and `check-format-output-files` now list files and match `paths-ignore` through `check-common/diffscope.py` (gha#1856).
  A file name holding a double quote, a backslash, or a tab is now checked, since the listing runs `git ls-files -z` (gha#1923).
  In `paths-ignore`, `*` no longer matches across a `/`, and a bare directory name such as `docs` now skips everything under it, as in the other checks.
  Run outside a git checkout, either check now stops with a named error instead of a Python traceback.
