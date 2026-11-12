- `check-merge-drops` now takes its path-ignore helpers from `check-common/diffscope.py` instead of carrying its own copies (gha#1856).
- `check-typed-output` now takes its git, listing, and path-ignore helpers from `check-common/diffscope.py` instead of carrying its own copies (gha#1856).
  A diff-scoped run now decodes a file name git quotes in the diff header or in `git status`,
  so a changed file whose name holds `"`, a backslash, or a tab is no longer dropped,
  and it is not thrown off by a caller's `diff.mnemonicPrefix` or `diff.noprefix` setting.
