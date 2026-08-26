- **`claude-code-review` splits the model job from posting credentials**
  ([#580](https://github.com/Morrison-Lab/gha/issues/580)).
  The reviewer deny list cannot be a security boundary once `Bash` is
  granted whole (wrapping a denied command, or writing through a redirect,
  both go around it).
  `claude-review` now runs the model with `contents: read` (plus
  `pull-requests: read`, `issues: read`, and `actions: read`),
  writes the review to an artifact, and forwards `github.token` to
  `claude-code-action` so the action's OIDC App-token exchange is skipped --
  that exchange's `DEFAULT_PERMISSIONS` are contents/pull_requests/issues
  write, and `additional_permissions` merges on top of those defaults
  rather than replacing them
  (anthropics/claude-code-action v1.0.196 `src/github/token.ts`,
  measured 2026-08-26).
  `id-token: write` is omitted from the model job:
  forwarding `github_token` skips `getIDToken()`, and granting the
  permission would let a dropped override mint that write token.
  `post-review` downloads the artifact and posts;
  it holds `pull-requests: write` / `issues: write`
  and `actions: read`, and does not invoke the model.
  Callers must grant `actions: read` too: a `permissions:` block sets
  unspecified scopes to none, and without it artifact download 403s.
  A missing artifact after a failed review still posts the gha#543
  failure notice (empty payload fields normalize to unknown).
  `gather-context` also holds those write grants (stash/early notice) but
  never runs the model.
  `classify_inline_comments: false` restores during-session posting and
  skips the post-session classify-and-post step
  (anthropics/claude-code-action #1048).
  Immediate posts are a no-op because the inline-comment MCP tool is not
  allowlisted; skipping the post-step is the point, so a leftover buffer
  cannot 403 on this read-only token.
  Tag mode (`track-progress: true`) is ignored for the same reason; the
  input is kept so existing callers do not fail at the call gate.
  The posting job is `pull_request_target`-free: forks are already refused
  (gha#235), so same-repo `pull_request` / `workflow_dispatch` is enough.
