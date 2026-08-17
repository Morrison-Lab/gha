- **`gemini-code-review.yml` and `gemini.yml` now specify `mcp_github_` prefixes
  for MCP tools in prompts**
  ([#463](https://github.com/Morrison-Lab/gha/issues/463)).
  The Gemini CLI registers tools exposed by the GitHub MCP server with an
  `mcp_github_` prefix (`mcp_github_pull_request_read`,
  `mcp_github_pull_request_review_write`, `mcp_github_add_issue_comment`).
  Without the explicit prefix in the prompt instructions, Gemini failed to match
  the tool names, fell back to `run_shell_command` (which was denied by policy),
  and exhausted `maxSessionTurns`.
