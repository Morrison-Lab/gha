- **`annotation-gate` allows the annotations a recovered first review attempt leaves.**
  When the Claude Code install or the first review attempt failed and the retry recovered,
  the install error, the missing-execution-file messages and the recovery notice stayed on the run
  and failed the gate, which blocked pull requests whose review had completed.
  They are now in `default-allow`.
  A review that never recovers still fails its own job (gha#1412).
