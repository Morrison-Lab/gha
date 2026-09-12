- **check-phi / check-non-standard-chars / check-one-function-per-file / antigravity-review / check-diff-scoped**:
  Configure standard streams to safely encode non-ASCII characters with error replacement on non-UTF-8 consoles like Windows `cp1252`,
  preventing `UnicodeEncodeError` from falsely failing clean local scans ([#860](https://github.com/Morrison-Lab/gha/issues/860)).
