- `annotation-gate`: a `workflow_dispatch` gate no longer defers while another run on the commit is unfinished.
  It gates the commit with what has finished and posts the `annotation-gate` check run.
  Before, a manual dispatch with `defer-while-running` exited green and posted nothing, since no later run would gate the commit (gha#1762).
