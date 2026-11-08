- **`annotation-gate` no longer cancels a gate job that has started.**
  The gate job's concurrency group and the caller stub set `cancel-in-progress: false`,
  so a newer completion on the same commit replaces only the gate waiting behind the running one.
  On Morrison-Lab/lds, 83 of 100 gate runs on one commit were cancelled,
  one of them nine seconds after its job started and before its first step,
  and the commit had no `annotation-gate` check run nine hours after the merge (gha#1649).
  A caller that sets `cancel-in-progress: true` on its own workflow-level group keeps the old behaviour until it changes it.
