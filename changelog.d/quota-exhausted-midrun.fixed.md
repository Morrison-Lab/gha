- `claude-code-review`: a review whose account quota runs out **part-way
  through** the run now skips gracefully instead of failing the check. The
  graceful-skip path previously recognized only a request rejected before any
  work (`total_cost_usd: 0`, `num_turns: 1`), so an exhaustion reached mid-review
  -- real turns, real cost, `api_error_status: 429` -- reddened `claude-review`
  and `require-review` over an account condition the PR's author could not act
  on, with no comment explaining why. It now posts the same quota comment the
  pre-flight path does, and skips the retry attempt rather than re-spending on a
  call the API will reject until the limit resets
  ([#520](https://github.com/Morrison-Lab/gha/issues/520)).
