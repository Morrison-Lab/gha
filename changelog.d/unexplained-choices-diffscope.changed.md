- `check-unexplained-choices` now imports its git, diff, file, and path-ignore helpers from `check-common/diffscope.py` instead of carrying its own copies (gha#1856).
  Its whole-tree listing picks up `-z`, and its diff parser now decodes quoted paths.
