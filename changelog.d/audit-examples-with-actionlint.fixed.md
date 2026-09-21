- **`_selftest.yml` audits `examples/*.yml` with `actionlint`** (#840).
  `actionlint` without arguments audits only `.github/workflows/`, leaving
  example caller stubs unlinted in CI.
  The `lint-workflows` job in `_selftest.yml` now passes `examples/*.yml` to
  `actionlint -shellcheck ""`, ensuring all caller stubs are validated
  against GitHub Actions schema, expression syntax, and reusable workflow
  caller contracts.
