- **Documented why a re-run cannot verify a major-tag slide** in `CLAUDE.md`.
  GitHub resolves a `uses:` reusable-workflow reference once, at run creation,
  and records it in `referenced_workflows`; a re-run replays that SHA, so it
  keeps executing the pre-slide workflow.
  Composite actions nested inside the reusable workflow *do* re-resolve at
  job-preparation time, so a re-run mixes new-version composites with the old
  reusable workflow and reads as "the fix is live and didn't work".
  The entry gives the mechanical check (`referenced_workflows[].sha`) and the
  fix (trigger a fresh run, not a re-run).
