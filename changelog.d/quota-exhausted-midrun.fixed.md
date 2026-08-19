- `claude-code-review`: a review whose account quota runs out now skips
  gracefully instead of failing the check, whether the API rejects the request
  at the door or part-way through the run.
  Two gaps combined to redden `claude-review` and `require-review` over an
  account condition the PR's author could not act on.
  The guard recognized only a pre-flight rejection
  (`total_cost_usd: 0`, `num_turns: 1`),
  so an exhaustion reached mid-review --- real turns, real cost,
  `api_error_status: 429` --- fell through to its hard-error exit.
  And the `Run Claude Code Review` step lacked `continue-on-error`,
  so the action's own exit 1 failed the job even when the guard did conclude
  a graceful skip, leaving that path unreachable for any exhaustion that got
  past the pre-flight check
  ([#520](https://github.com/Morrison-Lab/gha/issues/520)).
