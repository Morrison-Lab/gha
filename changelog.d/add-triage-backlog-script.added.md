- **`triage-backlog/` holds the backlog triage script and its tests** (#1900).
  The script is copied unchanged from `Morrison-Lab/ai-config`'s `scripts/triage-backlog.py`.
  It gives each open issue one of `P1`, `P2` or `P3` and, with `--labels-only`, closes nothing.
  The reusable workflow that runs it comes in a later pull request.
