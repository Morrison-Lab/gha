- **`preview` and `quarto-publish` find the runner's Quarto when
  `preinstalled-toolchain` is `true`.**
  A self-hosted runner's service has no login `PATH`, so a Quarto installed
  under the runner user's home failed with `quarto: command not found`.
  A new step adds `/home/morri313/opt/quarto-1.10.18/bin` to `GITHUB_PATH`
  when `quarto` is not already on `PATH` and that directory holds it.
  Hosted runners and runners with Quarto on `PATH` are unchanged.
