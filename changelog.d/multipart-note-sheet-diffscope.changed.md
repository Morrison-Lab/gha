- `check-multipart-exercises` and `check-note-sheet-rows` now import their git calls, diff parser, file reader, and path-ignore helpers from `check-common/diffscope.py` instead of carrying their own copies (gha#1856).
  Both pick up `-z` file listing and unquoting of quoted paths in the diff, which those copies lacked.
