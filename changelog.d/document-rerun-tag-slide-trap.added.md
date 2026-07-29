- **Documented which re-run modes can verify a major-tag slide** in `CLAUDE.md`.
  GitHub records a `uses:` reusable-workflow reference in `referenced_workflows`
  at run creation.
  Per GitHub's docs, re-running *failed jobs* or a *specific job* replays that
  SHA, so it keeps executing the pre-slide workflow, while re-running *all
  jobs* re-resolves the reference.
  Composite actions nested inside the reusable workflow re-resolve at
  job-preparation time either way, so a failed-jobs re-run mixes new-version
  composites with the old reusable workflow and reads as "the fix is live and
  didn't work".
  The entry gives the mechanical check (`referenced_workflows[].sha`) and
  recommends a fresh run as the unambiguous way to verify a slide.
