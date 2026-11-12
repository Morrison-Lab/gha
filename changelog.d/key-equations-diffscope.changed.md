- `check-key-equations-displayed` now imports its git calls and diff parser from `check-common/diffscope.py` instead of carrying its own copies (gha#1856).
  Its whole-tree listing picks up `-z`, and its diff parser now decodes quoted paths and uses hunk counts, both of which the copy lacked.
