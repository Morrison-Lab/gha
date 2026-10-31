- `lint-changed-files`, `update-snapshots` and `version-check` take `preinstalled-toolchain`
  (default `false`), as `spellcheck` does.
  When `true`, they skip `setup-r` and `setup-r-dependencies`, which need `sudo`.
  `lint-changed-files` and `update-snapshots` install the package's dependencies with pak into the user library.
  `update-snapshots` also skips the apt install and `setup-julia`, and puts the runner's Julia on `PATH`.
  A self-hosted runner that already has R, and no `sudo`, can now run these three workflows.
