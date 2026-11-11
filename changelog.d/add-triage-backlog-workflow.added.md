- **`triage-backlog.yml` is a new reusable workflow** (#1900).
  It calls the `triage-backlog` composite action, so it adds `P1`, `P2`, and `P3` labels and closes nothing.
  Its `dry-run` input defaults to `true`, and a scheduled caller passes `false` to label for real.
  The caller grants `issues: write`.
  Pin it at `@v3`.
