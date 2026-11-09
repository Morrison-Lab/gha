- `preview` has an opt-in `cluster-render` input (default `false`) that runs the render step through `condor-batch` in a cluster image and returns the site, `_freeze`, `.quarto`, and the render log.
  `preview.yml` forwards it with `cluster-head`, `cluster-image`, and `cluster-image-file` (gha#1618, gha#1563).
