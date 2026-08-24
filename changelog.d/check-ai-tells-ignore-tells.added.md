- **`check-ai-tells` now supports an `ignore-tells` input to suppress domain vocabulary**
  ([#619](https://github.com/Morrison-Lab/gha/issues/619)).
  Callers can provide a comma- or space-separated list of tell names to ignore
  (e.g. `robust, landscape`), preventing legitimate domain terminology from
  skewing density calculations and causing false-positive CI failures.
  Suppressed tells and their counts are reported in the scan summary line.
