- **`check-review-execution.sh` no longer false-positives a stub-review retry
  when the verdict was posted via a tool call** (#218). The script's stub
  detection scanned only assistant "text" blocks for a verdict line; a review
  that posts its verdict entirely through the inline-comment MCP tool
  (`mcp__github_inline_comment__create_inline_comment`'s `body`) or a
  `gh pr comment`/`gh api .../comments` Bash call — leaving only a narrative
  aside in its own text ("Posted a comment ending in `### Verdict: ...`") —
  is a genuinely complete review, but the line-start-anchored verdict regex
  correctly didn't match that narrative sentence, so the run was
  misclassified as a stub and retried unnecessarily. The scan now also
  covers those specific GitHub-posting tool calls' arguments, not just plain
  text blocks.
