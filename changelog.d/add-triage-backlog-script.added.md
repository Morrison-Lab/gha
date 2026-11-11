- **`triage-backlog/` holds the backlog triage script and its tests** (#1900).
  Both are copied from `Morrison-Lab/ai-config`'s `scripts/`, and `triage-backlog/README.md` lists the three lines that differ.
  The script gives each open issue a priority (`P1`, `P2`, or `P3`) or proposes closing it.
  With `--apply --labels-only`, it adds labels and closes nothing.
  The reusable workflow that runs it comes in a later pull request.
