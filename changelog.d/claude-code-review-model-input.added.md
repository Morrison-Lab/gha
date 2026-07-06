- **`claude-code-review.yml` gains a `model` input** (#186). Passed through to
  the underlying Claude Code CLI's `--model` flag (via the
  `run-claude-review-attempt` composite action), letting a consumer run the
  reviewer on a different model (e.g. Opus, for higher-confidence review at
  higher cost). Empty by default, which falls through to
  `claude-code-action`'s own default. `claude.yml` already exposes a generic
  `claude-args` passthrough that covers the same use case
  (`with: { claude-args: '--model ...' }`), so it needed no equivalent change.
