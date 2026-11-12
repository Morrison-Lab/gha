- `check-restated-results` now imports its git, file, and path-ignore helpers from `check-common/diffscope.py` instead of carrying its own copies (gha#1856).
  Its tracked-file listing picks up `-z`, so a page whose name holds a quote or a backslash is no longer skipped.
