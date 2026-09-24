- **Flag every qualifying quoted literal in an `in (...)` membership list for `study_id`**,
  rather than only the first element ([gha#926](https://github.com/Morrison-Lab/gha/issues/926)).
  Track multi-line `in (...)` lists across lines until their closing paren.
  Add a value-keyed second sweep across scanned lines for any flagged `study_id` values,
  catching bare pasted listings in comments or proc print output.
