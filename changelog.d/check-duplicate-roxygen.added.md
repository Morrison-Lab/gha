- **`check-duplicate-roxygen`: add action to check for duplicate roxygen parameter documentation**
  ([#864](https://github.com/Morrison-Lab/gha/issues/864)).
  New composite action and reusable workflow scans R code files for duplicate roxygen2
  `@param` descriptions across functions and recommends consolidation using
  `@inheritParams` or `@inheritDotParams`.
