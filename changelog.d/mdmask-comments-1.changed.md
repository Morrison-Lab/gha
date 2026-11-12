- `check-common/mdmask.py` gains `replace_comments`, which removes or replaces each closed HTML comment
  with a `find` scan instead of a regex (gha#1856).
  `check-definition-equations`, `check-restated-results`, `check-extracted-lemmas`, `check-hybrid-sentences`,
  `check-split-solutions`, `check-exercise-question-paragraph`, and `check-result-definition-links` use it
  in place of their own comment patterns, with the same output.
