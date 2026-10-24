- `preview` and `quarto-publish` take a `preinstalled-toolchain` input (default `false`).
  When true they skip installing Quarto, R, Julia, Chrome and apt packages and install `r-packages` with pak,
  so a self-hosted runner without sudo can build a site ([#1167](https://github.com/Morrison-Lab/gha/issues/1167)).
