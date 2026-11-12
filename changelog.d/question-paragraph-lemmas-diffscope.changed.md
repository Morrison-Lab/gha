- `check-exercise-question-paragraph` and `check-extracted-lemmas` now import their git calls and diff parser from `check-common/diffscope.py` instead of carrying their own copies (gha#1856).
  Both pick up `-z` file listing and unquoting of quoted paths in the diff, which those copies lacked.
