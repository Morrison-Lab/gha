- `check-div-ids`, `check-single-ask-parts`, `check-unexplained-choices`, `check-unexplained-contrasts`,
  `check-one-div-per-subfile`, `check-solution-citations`, `check-multipart-exercises`, and `check-def-commentary`
  now take their code-span pattern from `check-common/mdmask.py` (gha#1856).
  Their old pattern closed a span on the first backtick of a longer run,
  so a one-backtick span that held two backticks in a row ended early;
  a span now closes only on a run of the same length.
