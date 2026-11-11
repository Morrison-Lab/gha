- Nine checks that borrowed their git and file helpers from `check-one-div-per-subfile` now import them from `check-common/diffscope.py` (gha#1856):
  `check-axis-titles`, `check-contour-3d`, `check-exm-figures`, `check-figure-placement`, `check-heading-levels`,
  `check-self-contained-captions`, `check-static-figures`, `check-tree-lists` and `check-visualization-figures`.
  They still load `check-one-div-per-subfile` for its div and fence parsing.
