- **`annotation-gate` gates the triggering run at the attempt its event reports.**
  With `all-runs`, the runs listing can lag a re-run by seconds and still show the previous attempt.
  A gate started by a passing last attempt then read the timeout annotations of the attempts before it
  and failed the commit (gha#1620).
