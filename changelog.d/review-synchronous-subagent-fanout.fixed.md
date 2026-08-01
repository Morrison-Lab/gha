- `claude-code-review`: the reviewer no longer ends its run waiting on
  background sub-agents instead of posting a verdict. Its prompt already
  forbade deferring work past the end of the run, but carved out the
  `code-review` plugin's own parallel sub-agent fan-out as safe. That
  carve-out was too broad: `Agent`'s `run_in_background` parameter defaults
  to `true`, so the blessed fan-out was itself a background spawn, and the
  model ended its turn waiting for completion notifications that only a
  later turn can deliver. The prompt now requires `run_in_background: false`
  on every `Agent`/`Task` call, which keeps the parallelism and removes the
  deferral. Observed on `Morrison-Lab/ai-config#986`, run `30671528617`:
  eight `Agent` calls, `is_error: false`, `stop_reason: end_turn`, $9.76
  spent, and a final message of "Waiting for the remaining background agents
  to complete." where the verdict should have been (gha#392).
