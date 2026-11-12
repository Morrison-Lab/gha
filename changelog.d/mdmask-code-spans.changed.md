- `check-key-equations-displayed`, `check-definite-antecedents`, `check-quarto-prose`, and `check-literal-math-letters` now take their code-span masking from `check-common/mdmask.py` (gha#1856).
  The shared pattern closes a span only on a backtick run of the same length, as CommonMark does,
  so a double-backtick span holding a single backtick is masked whole in every check that uses it.
