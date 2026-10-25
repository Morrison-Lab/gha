- **`spellcheck`** (action and reusable workflow) --
  takes `preinstalled-toolchain` (default `false`).
  When `true`, it skips `setup-r` and `setup-r-dependencies`, which need `sudo`,
  and installs `{spelling}` with pak into the user library if it is missing,
  so the check runs on a self-hosted runner that already has R and the pak package.
