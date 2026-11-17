- The diff-scoped checks treat a line whose only change is British to American spelling
  as unchanged, so a spelling fix no longer makes them reflag what the line already held
  (gha#2095).
  `check-common/diffscope.parse_diff` records each deleted line's American respellings
  as deleted too, so the moved-line test passes the fix,
  and `check-definition-equations`, which judges moved lines,
  drops spelling-only lines through `diffscope.spelling_only_lines`.
  The word list moved to `check-common/spelling.py`, shared with `check-avoided-words`.
