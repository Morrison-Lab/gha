- **A deferred annotation gate now names the runs it waits on.**
  When `defer-while-running` holds the gate because other runs on the head are
  still queued or in progress, the gate prints a `::notice::` and writes a
  step-summary list naming each of those runs, its status, how many minutes it
  has waited, and its link.
  Before, the run log said only how many runs were unfinished, so a gate held
  behind a full self-hosted pool looked like a gate that never posted
  ([gha#2151](https://github.com/Morrison-Lab/gha/issues/2151)).
