- **`run-check/run-check.sh`**, a wrapper that runs one check inside a bundled
  `condor-batch` job.
  It groups the output, adds the check's name as `title=` to every annotation,
  appends a pass/fail row to the step summary, and keeps the check's exit code.
  Many small checks can then share one HTCondor job instead of each taking a
  runner (lds#1839, a private repository).
