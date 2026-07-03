- **`claude-code-review.yml`'s review guard no longer red-X's every review in
  this repo's own dogfooding setup.** #191's guard-script checkout resolves
  this reusable workflow's own repo/ref via `github.job_workflow_ref`, but
  that context value is a documented no-op for a **same-repository**
  reusable-workflow call (only a genuine cross-repo `owner/repo/...@ref` call
  populates it) — exactly `claude-review.yml` calling `claude-code-review.yml`
  within `d-morrison/gha` itself, which #191's own description already
  flagged as untestable from gha's own CI. The empty value crashed the new
  `parse-workflow-ref` step before the review's `### Verdict` could even be
  checked, red-X'ing `require-review` on every PR regardless of its content.
  Skip the redundant checkout when `github.job_workflow_ref` is empty — a
  same-repo call means the workflow's initial checkout already IS this
  reusable workflow's own tree, so the guard script is already present at its
  normal path. Cross-repo consumers (where the context value populates
  correctly) are unaffected.
