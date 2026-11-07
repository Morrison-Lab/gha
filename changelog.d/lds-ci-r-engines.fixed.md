- **`ranger`, `xgboost`, and `DT` in the `lds-ci.sif` definition.**
  A full-site render on the cluster image failed at `trees-lab.qmd` with
  "Please install the ranger package to use this engine", because the
  `rand_forest()` and `boost_tree()` engines need `ranger` and `xgboost`.
  `DT` is called by a page in the `latex-macros` submodule
  ([gha#1431](https://github.com/Morrison-Lab/gha/issues/1431)).
