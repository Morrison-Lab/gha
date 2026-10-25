- **`check-links`** --
  makes `lychee` reachable from a login shell,
  because `lychee-action` runs its entrypoint with `bash -l`,
  and on Debian `/etc/profile` resets the `PATH` that holds lychee's install directory
  (`lychee: command not found`, exit 127), so no link check could run on a self-hosted Debian runner.
  A small shim in `~/.local/bin` finds the binary through `$RUNNER_TEMP` when it runs.
