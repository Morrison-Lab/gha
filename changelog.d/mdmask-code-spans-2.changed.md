- `check-term-links`, `check-self-credits`, `check-self-contained-captions`, `check-informal-definitions`,
  `check-extracted-lemmas`, and `check-exercise-question-paragraph` now take their code-span masking
  from `check-common/mdmask.py` (gha#1856).
  A span now closes only on a backtick run of the same length in each of them.
