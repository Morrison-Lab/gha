- **`run-review-job-split-tests.py` checks declared-vs-consumed outputs for
  every composite `claude-code-review.yml` reads, not only
  `run-review-guard`** (#806, #853).
  The gha#804 assertion was scoped to the `fail-check*` step-id prefix;
  it is now derived from the parsed workflow (every step whose `uses:` names
  a `Morrison-Lab/gha/.github/actions/<x>@...` or `./.github/actions/<x>`
  path), every `steps.<id>.outputs.<name>` read is asserted against that
  action's `outputs:`, the pair count is reported and a zero count fails,
  and a step id naming two different composites is refused.
  The suite's `--guard` flag is replaced by `--actions-dir`
  (default `.github/actions`).
  The widened check found no undeclared output on `main` (38 pairs across
  12 composites).
