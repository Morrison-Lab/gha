- **`run-review-job-split-tests.py` checks declared-vs-consumed outputs for
  every in-repo composite `claude-code-review.yml` reads,
  extending the previous `run-review-guard`-only check** (#806).
  The gha#804 assertion was scoped to the `fail-check*` step-id prefix.
  The check now scans the workflow for steps whose `uses:` names an in-repo
  action (`Morrison-Lab/gha/.github/actions/<x>@...` or
  `./.github/actions/<x>`, nested paths included, matched
  case-insensitively).
  Every `steps.<id>.outputs.<name>` read is asserted against that action's
  `outputs:` block.
  A step id naming two different composites is refused, and a scan that
  matched no pair at all fails instead of passing vacuously.
  A read whose step id no step declares is now refused instead of skipped:
  GitHub resolves it to the empty string, so its consumer is silently inert.
  The suite's `--guard` flag is replaced by `--actions-dir`
  (default `.github/actions`).
  The widened check found no undeclared output and no dangling read on
  `main` (38 pairs across 12 composites).
