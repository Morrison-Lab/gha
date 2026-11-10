- `update-snapshots` uses the runner's own R and pak when `preinstalled-toolchain` is false
  but the runner has no passwordless sudo and already has R with pak.
  It no longer fails in `r-lib/actions/setup-r` at `sudo apt-get update`.
  Without a runner R it warns that setup-r will fail (gha#1706).
