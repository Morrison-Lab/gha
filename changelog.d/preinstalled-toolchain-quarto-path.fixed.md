- **`preview` and `quarto-publish` find the runner's Quarto when
  `preinstalled-toolchain` is `true`.**
  A self-hosted runner's service has no login `PATH`, so a Quarto unpacked under
  the runner user's home failed with `quarto: command not found`.
  A new step adds the newest `~/opt/quarto-<version>/bin` to `GITHUB_PATH`
  when `quarto` is not already on `PATH` and such a directory exists.
  Hosted runners and runners with Quarto on `PATH` are unchanged.
