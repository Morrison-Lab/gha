- `check-hybrid-sentences`:
  flag a hybrid sentence whose connective follows a comma, as in "The risk is zero, and `x = 1`".
  `check-hybrid-sentences` and `check-definition-equations` also pass explicit
  `--src-prefix=a/ --dst-prefix=b/` to `git diff`, so a user's `diff.mnemonicPrefix` or
  `diff.noprefix` setting no longer makes every file silently skipped
  ([#1347](https://github.com/Morrison-Lab/gha/issues/1347)).
