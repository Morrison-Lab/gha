- **`scripts/register-self-hosted-runner.sh`** --
  registers one self-hosted runner for an organization on a Linux host,
  without sudo.
  It joins a runner group that admits private repositories only
  and refuses an existing group that admits public ones,
  mints the registration token with the local `gh` login,
  and verifies the runner tarball's SHA-256
  ([#1167](https://github.com/Morrison-Lab/gha/issues/1167)).
