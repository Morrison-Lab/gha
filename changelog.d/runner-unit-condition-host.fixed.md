- **`scripts/install-runner-systemd-unit.sh` pins each runner unit to one host** --
  cf463-01 and cf463-02 share one home, so an enabled unit was enabled on both,
  and both started a listener for the same runner.
  Each instance now gets a drop-in with `ConditionHost=` for the installing host (or `RUNNER_HOST`),
  so the other host's user manager skips it
  ([#1543](https://github.com/Morrison-Lab/gha/issues/1543)).
