- `check-serial-comma` now imports its git calls and diff parser from `check-common/diffscope.py` instead of carrying its own copies (gha#1856).
  Its whole-tree listing picks up `-z`, and its diff parser now decodes quoted paths and ends each hunk by its count.
  The copy read an added line beginning with `++` and a space as a file header.
