- `check-typos` now takes its path-ignore helpers from `check-common/diffscope.py` instead of carrying its own copies (gha#1856).
  A diff-scoped run now decodes a file name git quotes in the diff header,
  so the added lines of a file whose name holds `"`, a backslash, or a tab are no longer dropped.
