- **`claude.yml` and `claude-code-review.yml` now post the run's dollar cost
  in a PR comment**, via a new `report-cost` input that defaults `true` -- a
  behavior change for every existing `@v2` consumer, not an opt-in addition.
  `anthropics/claude-code-action` computes each run's cost (`total_cost_usd`)
  but never surfaces it in a comment (see README.md's feature-parity table
  for the upstream source citation); both workflows now extract that field
  and surface it themselves: `claude-code-review.yml` posts a follow-up
  comment linking back to the review (summed across the initial attempt and
  any gha#185 stub-review retry); `claude.yml` appends a cost line to its
  existing response and issue-trigger finalize comments, and posts a small
  standalone comment on the one commit-and-dispatch path that otherwise posts
  none. Set `report-cost: false` to suppress it (#219).
