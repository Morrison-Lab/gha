- Removed the invalid `timeout-minutes` key from the two dogfood caller
  jobs (`.github/workflows/opencode-review.yml`,
  `.github/workflows/gemini-review.yml`): GitHub rejects a job that calls a
  reusable workflow at parse time when it carries the key, so every
  `gemini-review.yml` dispatch had been failing instantly with zero jobs
  (#599).
