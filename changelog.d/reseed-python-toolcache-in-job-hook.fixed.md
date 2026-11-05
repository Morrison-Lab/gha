- The job-started hook `scripts/check-runner-disk.sh` now seeds the system Python into the runner's tool cache,
  so a runner whose work folder was moved after registration no longer fails `actions/setup-python` on Debian 13 (gha#1205).
  A seeding failure warns and does not fail the job.
