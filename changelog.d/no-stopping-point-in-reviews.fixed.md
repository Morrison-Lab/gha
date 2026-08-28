- **Reviewer prompt: no terminal Stopping Point declarations** --
  `run-claude-review-attempt` now instructs the reviewer that its final
  message is a posted review artifact, not a terminal session recap, so
  it must end with the `### Verdict` line rather than a session-recap
  "Stopping Point" declaration
  ([#694](https://github.com/Morrison-Lab/gha/issues/694)).
