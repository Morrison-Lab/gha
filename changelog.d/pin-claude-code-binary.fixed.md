- `run-claude-review-attempt` passes a version-pinned Claude Code binary to
  `claude-code-action` through `path_to_claude_code_executable` when one is
  installed on the runner and matches its recorded digest, so concurrent
  reviews on runners that share one home directory no longer collide
  installing it (gha#1704).
  Elsewhere the action installs Claude Code itself, as before.
