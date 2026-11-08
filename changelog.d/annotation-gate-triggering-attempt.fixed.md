`annotation-gate` with `all-runs` gates the run that triggered it at no earlier attempt than the event reports.
The runs listing can lag a re-run by seconds and still show the previous attempt,
so a gate started by a passing last attempt read the timeout annotations of the attempts before it and failed the commit (gha#1620).
