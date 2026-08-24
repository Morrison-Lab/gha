- **`_selftest.yml` now audits `.github/workflows/` with `actionlint`** ([#591](https://github.com/Morrison-Lab/gha/issues/591)).
  Prevents invalid workflow schema regressions
  (such as invalid caller job keys; [#582](https://github.com/Morrison-Lab/gha/issues/582))
  from shipping to `main`.
