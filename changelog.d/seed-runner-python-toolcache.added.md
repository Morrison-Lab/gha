- `scripts/seed-runner-python-toolcache.sh` puts the system Python into a self-hosted runner's toolcache,
  so `actions/setup-python` works on a distribution it publishes no build for (Debian 13).
  `register-self-hosted-runner.sh` runs it before starting the runner.
