- **`check-new-line-breaks` now emits `::error` annotations instead of `::warning`** for detected semantic line break violations.
  Findings now show up as error annotations on PR diffs,
  with the check blocking by default (`fail: true`).
