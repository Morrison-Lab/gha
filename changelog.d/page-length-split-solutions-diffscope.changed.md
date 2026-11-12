- `check-page-length` and `check-split-solutions` now import their git, diff, and path-ignore helpers from `check-common/diffscope.py` instead of carrying their own copies (gha#1856).
  Their tracked-file listings pick up `-z`, and their diff parsers decode quoted paths, so a page whose name holds a quote or a backslash is no longer skipped.
