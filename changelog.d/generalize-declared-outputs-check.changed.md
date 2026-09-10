- **`run-review-job-split-tests.py` checks declared-vs-consumed outputs for
  every in-repo composite `claude-code-review.yml` reads, not only
  `run-review-guard`** (#806, #853).
  The gha#804 assertion was scoped to the `fail-check*` step-id prefix.
  It is now derived from the parsed workflow: every step whose `uses:` names
  a `Morrison-Lab/gha/.github/actions/<x>@...` or `./.github/actions/<x>`
  path (nested paths included, matched case-insensitively) is mapped, every
  `steps.<id>.outputs.<name>` read is asserted against
  that action's `outputs:`, the pair count is reported and a zero count
  fails, and a step id naming two different composites is refused.
  A read whose step id no step declares is now refused rather than skipped:
  GitHub resolves it to the empty string, so its consumer is silently inert.
  The suite's `--guard` flag is replaced by `--actions-dir`
  (default `.github/actions`).
  The widened check found no undeclared output and no dangling read on
  `main` (38 pairs across 12 composites).
