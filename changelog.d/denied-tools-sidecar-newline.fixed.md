- `claude-code-review.yml`: ensure the `denied_tools` output heredoc terminates
  on a new line when unpacking the review payload artifact (#764).
  `pack-review-payload.sh` now appends a trailing newline to `denied_tools.txt`,
  and `claude-code-review.yml` checks for a trailing newline before emitting the closing heredoc delimiter,
  preventing value truncation into the delimiter line.
  `compose-review-failure-report.sh` now distinguishes known non-zero denial counts
  with unavailable tool names from runs with no denial data recorded.
