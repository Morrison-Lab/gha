- **`claude-code-review.yml`'s fail-check guard still failed to locate
  `check-review-execution.sh` on real consumer runs** (#196), even after #191's
  fix. #191 resolved d-morrison/gha's own repo/ref via
  `github.job_workflow_ref` and checked it out into a side directory before
  running the script -- but that context variable came back empty at the call
  site in production, despite being passed correctly in the YAML, so the
  second `parse-workflow-ref` invocation failed with
  `usage: parse-workflow-ref.sh` and the whole guard step errored. The fix
  was only unit-tested via the sed-parsing logic in isolation, never
  exercised end-to-end. The guard now runs through a new composite action,
  `.github/actions/run-review-guard/`, that locates the script via
  `github.action_path` instead -- reachable regardless of how the calling
  reusable workflow was invoked, the same reasoning `parse-workflow-ref`
  itself relies on. `_selftest.yml`'s `review-fail-check` job now also
  exercises this composite action end-to-end via a real `uses:` step, closing
  the testing gap that let #196 slip through.
