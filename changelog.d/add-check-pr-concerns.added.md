- `check-pr-concerns`:
  add a diff-scoped, blocking composite action and reusable workflow that fails a pull request changing both content paths and infrastructure paths
  ([#1188](https://github.com/Morrison-Lab/gha/issues/1188)).
  Content and infrastructure go in separate PRs, and a path-based mix is the part of "one concern per PR" a check can decide.
  The `mixed-ok` label, read live through the API, lifts the check.
  Like its siblings it skips rather than examining the whole tree when there is no base to diff against.
