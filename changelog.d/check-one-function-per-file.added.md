- **`check-one-function-per-file`: add action to enforce one-function-definition-per-file rule**
  ([#801](https://github.com/Morrison-Lab/gha/issues/801)).
  New composite action and reusable workflow scans code files (.R, .py, .sh, .js, .ts, .jl)
  to ensure files define at most one top-level function, with header opt-out comment support.
