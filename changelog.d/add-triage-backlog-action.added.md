- **`triage-backlog` is now a composite action** (#1900).
  It runs `triage-backlog.py` with `--apply --labels-only`, so it adds `P1`, `P2` and `P3` labels and closes nothing.
  Its `dry-run` input defaults to `true` and is read fail-closed: only an explicit `false` changes labels.
  It copies the script's summary into the job summary, and warns when the open-issue count is over the `ceiling` input.
  The reusable workflow that calls it comes in a later pull request, after the `v3` tag includes the action.
