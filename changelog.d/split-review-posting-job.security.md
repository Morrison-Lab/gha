- **`claude-code-review` splits the model job from posting credentials**
  ([#580](https://github.com/Morrison-Lab/gha/issues/580)).
  The reviewer deny list cannot be a security boundary once `Bash` is
  granted whole (wrapping a denied command, or writing through a redirect,
  both go around it).
  `claude-review` now runs the model with `contents: read` (plus
  `pull-requests: read`, `issues: read`, `actions: read`, and
  `id-token: write`), writes the review to an artifact, and forwards
  `github.token` to `claude-code-action` so the action's OIDC App-token
  exchange is skipped -- that exchange's `DEFAULT_PERMISSIONS` are
  contents/pull_requests/issues write, and `additional_permissions`
  merges on top of those defaults rather than replacing them
  (anthropics/claude-code-action v1.0.196 `src/github/token.ts`,
  measured 2026-08-26).
  `post-review` downloads the artifact and posts; it holds
  `pull-requests: write` / `issues: write` and does not invoke the model.
  `gather-context` also holds those write grants (stash/early notice) but
  never runs the model.
  Inline comments during the model turn are dropped
  (`classify_inline_comments: false`; the inline-comment MCP tool is not
  allowlisted): posting them would need a writable token in the model job.
  Tag mode (`track-progress: true`) is ignored for the same reason; the
  input is kept so existing callers do not fail at the call gate.
  The posting job is `pull_request_target`-free: forks are already refused
  (gha#235), so same-repo `pull_request` / `workflow_dispatch` is enough.
