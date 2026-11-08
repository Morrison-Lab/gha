- `check-secrets`, `check-typos`, and `lint-workflows`: the tool downloads (gitleaks, typos, actionlint) retry up to 8 times, 10 seconds apart, and retry on any error with `--retry-all-errors`.
  Before, `check-secrets` and `check-typos` gave up after 3 tries 2 seconds apart, and `lint-workflows` never retried, so a burst of 403 or 504 responses from GitHub release downloads on the shared runner address failed the job with curl exit 22 (gha#1667).
  `--retry` alone does not retry a 403, which is how a rate-limited download answers.
