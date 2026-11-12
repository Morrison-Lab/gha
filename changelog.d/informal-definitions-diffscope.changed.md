- `check-informal-definitions` now takes its git, diff, and path-ignore helpers from `check-common/diffscope.py` instead of carrying its own copies (gha#1856).
  A diff-scoped run now reads a quoted file name in the diff header,
  and is not thrown off by a caller's `diff.mnemonicPrefix` or `diff.noprefix` setting.
