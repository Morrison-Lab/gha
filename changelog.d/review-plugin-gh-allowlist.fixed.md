- **`claude-code-review.yml`'s reviewer now gets the `gh` subcommands the
  `code-review` plugin itself needs.** The upstream `code-review@claude-code-plugins`
  plugin's own `/code-review` command declares `gh pr view`, `gh pr diff`,
  `gh pr list`, `gh issue view`, `gh issue list`, and `gh search` (plus
  `gh pr comment`) as tools it uses, but this workflow's `claude_args`
  allowlist never granted any of them -- every one of the plugin's 4 parallel
  sub-agents hit a permission denial on each attempt. #187 already stopped a
  denial from ending a review early, but under a heavier prompt (e.g. a
  dispatched re-review carrying prior-review context) enough denials across
  all 4 sub-agents could still pile up that the run finished `is_error:false`
  with no `### Verdict` -- the same stub-review signature
  `check-review-execution.sh`'s guard (#172/#176) catches (reproduced with
  `permission_denials_count: 28` / `num_turns: 50` on a dispatched re-review
  of #183), red-X'ing `require-review` for a PR that was never actually
  reviewed. Grants the plugin's read-only `gh` subcommands; `gh pr comment`
  stays disallowed since this workflow posts the review itself (with its own
  dedup/collapse handling), and letting the plugin self-post risked duplicate
  or uncontrolled comments.
