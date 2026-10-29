- `lint-changed-lines` keeps the R already installed on a self-hosted runner instead of running `setup-r`.
  `setup-r` calls `sudo apt-get`, which fails on a runner without passwordless sudo.
