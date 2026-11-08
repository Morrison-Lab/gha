- `quarto-publish` has an opt-in `cluster-render` input (default `false`) that runs the render step through `condor-batch` in a cluster image and returns the site, `_freeze`, and `.quarto`.
  `quarto-publish.yml` forwards it with `cluster-head`, `cluster-image`, and `cluster-image-file` ([gha#1563](https://github.com/Morrison-Lab/gha/issues/1563)).
