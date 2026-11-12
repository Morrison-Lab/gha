- `check-function-graphs`, `check-self-contained-captions`, `check-page-length`, `check-quarto-links`, and `check-serial-comma`
  strip HTML comments with `check-common/mdmask.py`'s `replace_comments` instead of their own patterns (gha#1856),
  and the `drop_closed_comments` helpers in `check-one-div-per-subfile` and `check-definite-antecedents` call it too.
