- **Documented the `anthropics/claude-code-action` workflow-validation skip**
  in `CLAUDE.md`, alongside the existing self-review-skip guard section.
  When a PR edits the review workflow and the self-review skip is bypassed
  (e.g. an `@claude review` dispatch, as #417 attempted), the action's own
  content-validation still fires and gracefully skips, so `check-review-execution.sh`
  sees no execution output and `claude-review`/`require-review` go red with no
  verdict.
  The note records the diagnostic tells -- a sub-15s "no execution output"
  failure whose log shows `Workflow validation failed` /
  `Exiting due to workflow validation skip` rather than a literal `401`, so it
  is read from the step's raw output rather than grepped for a guessed string --
  and that a `github_token` override on the action is the real fix (proven via
  throwaway test PR #420).
