- `check-common/diffscope.py` now reads a path that git quotes, such as one holding `"`, a backslash, or a tab, and ignores a caller's `diff.mnemonicPrefix` and `diff.noprefix` settings (gha#1856).
  Before, such a file's added lines were filed under the quoted name and never checked,
  and either setting changed the `b/` prefix the parser strips.
  `check-write-idiom` already carried both fixes;
  `check-one-div-per-subfile` and the nine checks that use the module now have them too.
