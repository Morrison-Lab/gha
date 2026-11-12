- `check-code-messages` now imports its git calls and diff parser from `check-common/diffscope.py` instead of carrying its own copies (gha#1856).
  It picks up `-z` file listing, unquoting of quoted paths in the diff, and the pinned diff-prefix settings those copies lacked.
