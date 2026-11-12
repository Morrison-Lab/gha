- `check-orphaned-images` and `check-quarto-links` now import their git and path-ignore helpers from `check-common/diffscope.py` instead of carrying their own copies (gha#1856).
  Their behaviour is unchanged: both already listed files with `-z`.
