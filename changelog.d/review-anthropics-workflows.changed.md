- Audited central workflows (`claude.yml`, `claude-code-review.yml`,
  `gemini.yml`, `gemini-code-review.yml`, `antigravity-code-review.yml`,
  `jules-review.yml`, `ai-code-review.yml`) against official upstream
  repositories (`anthropics/claude-code-action` v1.0.191,
  `google-github-actions/run-gemini-cli` v0.1.22, `sanjay3290/jules-pr-reviewer`
  v1.0.2, and the `google-antigravity` SDK), confirming alignment on permissions,
  inputs, trusted-author gates, and PR execution parity ([#483](https://github.com/Morrison-Lab/gha/issues/483)).
