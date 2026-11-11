- `check-common/diffscope.py` now unquotes a path git quotes in a diff header or a rename line, such as one holding `"`, a backslash, or a tab (gha#1856).
  Before, such a file's added lines were filed under the quoted name.
  It also ignores a caller's `diff.mnemonicPrefix`, `diff.noprefix`, `diff.srcPrefix`, and `diff.dstPrefix` settings,
  any of which changed the `b/` prefix the parser strips.
  File lists read from `git ls-files` or `git diff --name-only` are still quoted;
  until they are unquoted too, a file with such a name is still skipped.
