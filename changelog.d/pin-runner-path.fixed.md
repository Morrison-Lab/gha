- **`scripts/register-self-hosted-runner.sh` keeps the runner's PATH** --
  before it starts a runner it runs the new `scripts/pin-runner-path.sh`,
  which copies the PATH that `config.sh` recorded in `.path` into `.env`.
  `nohup ./run.sh` passed on the caller's PATH instead,
  so a runner restarted from a bare shell or at reboot lost tools such as Quarto
  ([#1341](https://github.com/Morrison-Lab/gha/issues/1341)).
