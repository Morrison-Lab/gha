- **`slide-major-tag.yml` audits callee workflow permissions before sliding** (#836).
  Runs `audit_callee_permissions.py` against the active major tag to verify that
  no `workflow_call` reusable workflow has added permission keys or widened
  permission values (e.g. `read` -> `write` or `write-all`) since that tag.
  Callee permission widening breaks callers at startup time before jobs run,
  because a called workflow cannot request scopes its caller omitted.
  A `--force` input or `ALLOW_BREAKING_SLIDE=1` bypasses the check for emergency
  slides.
