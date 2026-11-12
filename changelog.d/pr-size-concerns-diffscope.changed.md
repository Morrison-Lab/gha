- `check-pr-size` and `check-pr-concerns` now take their git calls, file listings, and `paths-ignore` matching from `check-common/diffscope.py` (gha#1856).
  Both read git's listings with `-z`, so a file name holding a double quote, a backslash, or a tab is now matched against the globs as written rather than in git's quoted form (gha#1923).
  A bare directory name such as `docs` in `paths-ignore` now skips everything under it, as in the other checks.
