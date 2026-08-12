- `examples/claude-code-review.yml`: `dispatch-on-comment` can now accept an
  `@claude review` mention in addition to `/review`, for repos that have
  disabled the `claude.yml` agent.
  It is opt-in behind the repository variable `CLAUDE_AGENT_DISABLED`, which
  has to be set alongside the stub's `issue_comment` trigger -- the job only
  ever runs on that event, so the variable alone changes nothing.
  The default behaviour is unchanged: with the
  agent live, both workflows would answer the same mention and dispatch two
  paid reviews of possibly different heads
  ([UCD-SERG/serodynamics#277](https://github.com/UCD-SERG/serodynamics/issues/277)).
  Without it, a repo with the agent switched off had no mention path at all,
  and the phrasing people reach for produced a one-second run with every job
  skipped and nothing posted (#447).
  The match reuses the existing `detect-review-request` composite rather than a
  second inline pattern, so it inherits the code-span and fenced-block
  stripping (#344) and the tail-word set (#346).
