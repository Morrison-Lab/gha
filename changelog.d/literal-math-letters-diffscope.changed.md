- `check-literal-math-letters` now imports its git, diff, glob, and file helpers from `check-common/diffscope.py` instead of carrying its own copies (gha#1856).
  It also picks up fixes those copies lacked: unquoting quoted paths in the diff, `-z` file listing, and the pinned diff-prefix settings.
