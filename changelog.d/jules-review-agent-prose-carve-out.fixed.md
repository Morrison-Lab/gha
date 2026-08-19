- **`jules-review` no longer flags `CLAUDE.md` agent instructions as prompt injection**
  ([#373](https://github.com/Morrison-Lab/gha/issues/373)).
  The workflow's `extra_instructions` now tell Jules that imperative prose
  addressed to a future agent is the subject matter under review, while still
  reporting text aimed at this reviewer's verdict.
