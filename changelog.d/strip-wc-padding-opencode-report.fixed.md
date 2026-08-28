- **`report-opencode-run`: strip `wc -c` padding** --
  BSD/macOS `wc` pads its output with leading spaces, which
  `classify-opencode-run.sh` rejects as non-numeric; the byte count is now
  stripped at the source, matching `check-junk-files.sh`'s idiom
  ([#691](https://github.com/Morrison-Lab/gha/issues/691)).
