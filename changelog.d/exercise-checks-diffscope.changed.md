- `check-exercise-background` and `check-exercise-before-result` now import their git calls, diff parser, and path-ignore helpers from `check-common/diffscope.py` instead of carrying their own copies (gha#1856).
  Both pick up `-z` file listing and unquoting of quoted paths in the diff, which those copies lacked.
