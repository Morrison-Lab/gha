- `check-rubric-checklists` and `check-single-ask-parts` now import their git, diff, file, and path-ignore helpers from `check-common/diffscope.py` instead of carrying their own copies (gha#1856).
  Their whole-tree listings pick up `-z`, and their diff parsers now decode quoted paths.
