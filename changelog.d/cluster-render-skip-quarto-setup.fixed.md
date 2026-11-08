- `preview` and `quarto-publish` skip the runner-side Quarto install when the runner has no passwordless `sudo`
  and either Quarto is already on the `PATH` or `cluster-render` is on with the cluster ssh key present.
  The install runs `sudo`, which lab runners lack (gha#1642).
  A runner with `sudo` always installs, so a `condor-batch` fallback to a local render still finds Quarto.
