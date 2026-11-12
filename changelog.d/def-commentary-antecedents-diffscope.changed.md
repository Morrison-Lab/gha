- `check-def-commentary` and `check-definite-antecedents` now import their git calls, diff parser, path-ignore helpers, and file reader from `check-common/diffscope.py` instead of carrying their own copies (gha#1856).
  Both pick up `-z` file listing, unquoting of quoted paths in the diff, and the pinned diff-prefix settings those copies lacked.
