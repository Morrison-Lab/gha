- **`preview` and `quarto-publish` check `apt-packages` on a preinstalled toolchain** --
  with `preinstalled-toolchain: true` they skip apt, so a runner without `librsvg2-bin` failed minutes into the PDF pass.
  The new `scripts/check-preinstalled-apt-packages.sh` now fails the job at once, naming the runner,
  when a tool package (such as `librsvg2-bin`) is missing and its command is not on PATH.
  Any other missing package, such as a library from `preview`'s default list, is a warning,
  and with `cluster-render` a missing tool is a warning too
  ([#1758](https://github.com/Morrison-Lab/gha/issues/1758)).
