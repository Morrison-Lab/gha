- `annotation-gate` skips a job whose check run a re-run has superseded,
  so an annotation from an earlier attempt (such as a checkout error on a job
  that then passed on re-run) no longer fails the gate (gha#1722).
