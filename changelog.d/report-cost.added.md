- **`claude.yml` and `claude-code-review.yml`: new `report-cost` input, on by
  default.** `anthropics/claude-code-action` computes each run's dollar cost
  (`total_cost_usd`) but only writes it to the job step summary, never the PR
  comment it posts. Both workflows now extract that field and surface it in a
  comment instead: `claude-code-review.yml` posts a follow-up comment linking
  back to the review (summed across the initial attempt and any gha#185
  stub-review retry); `claude.yml` appends a cost line to its existing
  response and issue-trigger finalize comments. Set `report-cost: false` to
  suppress it (#219).
