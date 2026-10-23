- `lint-workflows` installs actionlint into a directory under `RUNNER_TEMP` instead of `/usr/local/bin`,
  so it runs on a self-hosted runner that has no sudo.
