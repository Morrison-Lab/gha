- **Log permission denials count unconditionally in `check-review-execution.sh`** ([#370](https://github.com/Morrison-Lab/gha/issues/370)).
  Ensures `permission_denials_count` and threshold metrics are logged unconditionally on step stdout
  and exported to `$GITHUB_OUTPUT`, while safely handling missing or non-integer values by defaulting to a high sentinel count.
