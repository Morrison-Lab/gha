- The `annotation-gate-run` example stub gives the run started by a gate run's own completion a concurrency group of its own (gha#1403).
  In the commit's group, that run, whose job is skipped, replaced the real gate waiting behind the running one, so the commit could go ungated.
