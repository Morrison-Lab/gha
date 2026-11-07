- **The runner job-started hook reports a busy or full host as a notice, not a warning** (#1584).
  `scripts/wait-runner-capacity.sh` ("still short after N minutes") and `scripts/prune-runner-workdir.sh` ("under N GB free") now emit `::notice::`.
  Both describe the host, not the code under test,
  so they report the host, not the code under test.
  The annotation gate enforces notices too, so it allows these two by default since #1603.
  Setup mistakes, such as a non-numeric limit, remain warnings.
