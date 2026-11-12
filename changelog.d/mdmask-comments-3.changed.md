- `check-math-definitions` and `check-source-overlap` strip HTML comments with `check-common/mdmask.py`'s `replace_comments`
  instead of their own patterns (gha#1856), so a composite action of either needs `check-common` beside it, as every other check does.
