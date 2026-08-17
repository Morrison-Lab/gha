- **Add diff-hunk line position validation for Antigravity review** ([#414](https://github.com/Morrison-Lab/gha/issues/414)).
  Parses `git diff` patch hunks in `run_antigravity.py` to verify that proposed inline
  review comments fall strictly within active diff hunk line ranges before API payload submission,
  preventing GitHub API HTTP 422 errors while preserving off-diff findings in the main report body.
