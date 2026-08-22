- Add `opencode-code-review.yml`, a read-only OpenCode PR review workflow that
runs the [opencode](https://opencode.ai) CLI headless (#586).
The diff is passed as a CLI attachment and the agent reads the checkout for
context with edits, shell, and web fetches denied; project-level opencode
config files are deleted from the checkout before the run so an untrusted PR
cannot override the deny rules.
Without an `OPENCODE_API_KEY` secret ([OpenCode Zen](https://opencode.ai/docs/zen/))
the workflow skips gracefully with a warning comment on the PR; a failed or
empty agent run posts a failure comment whose headline begins
`OpenCode review failed:` so `classify-review-delivery.sh` can recognize it.
`ai-code-review.yml` gains an `opencode` agent, an
`opencode-review-workflow-file` input, and `OPENCODE_API_KEY` passthrough.
