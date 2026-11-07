- **`annotation-gate` allows the runner job-started hook's own capacity and disk notices for every caller** (#1603).
  The gate enforces notices as well as warnings, so reporting a busy or full host as a notice (#1584) did not stop it failing a passing job, and each caller had to list the two messages.
  `default-allow` now covers `wait-runner-capacity: still short after N minutes` and `prune-runner-workdir: measured ... under N GB free`, anchored at the start of the message.
  A caller's `allow-patterns` entries for them can be removed.
