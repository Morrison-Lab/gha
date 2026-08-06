- **Documented the `anthropics/claude-code-action` workflow-validation skip**
  in `CLAUDE.md`, beside the existing `self_mod` self-review-skip guard.
  The `self_mod` guard skips the review when a PR edits the caller workflow
  `claude-review.yml` (dispatched or automatic alike), so such a PR gets a
  green, verdict-less skip today.
  That guard can also fail open on a transient `gh api` error (it reads
  `files=$(gh api ... || true)`), letting the review proceed on a PR that does
  edit the file -- or be bypassed deliberately, as gha#417 proposed and this
  repo rejected.
  Either way the action's own content-validation fires instead: it gracefully
  skips, `check-review-execution.sh` sees no execution output, and
  `claude-review`/`require-review` go red with no verdict.
  The note records the diagnostic tells -- the "Run Claude Code Review" step
  finishing in ~4-11s with no execution output, whose log shows
  `Workflow validation failed` / `Exiting due to workflow validation skip`
  rather than a literal `401` (so it is read from the step's raw output, not
  grepped for a guessed string) -- and that a `github_token` override on the
  action is the likely (untested) fix, since PR #420 only showed that bypassing
  the guard without one is counterproductive.
