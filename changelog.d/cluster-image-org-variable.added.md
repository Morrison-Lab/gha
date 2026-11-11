- **`preview.yml` and `quarto-publish.yml` read the cluster image from a variable** --
  an empty `cluster-image` now falls back to the caller's `CI_CLUSTER_IMAGE` Actions variable,
  and an empty `cluster-image-file` to `CI_CLUSTER_IMAGE_FILE`,
  so an org variable can move every caller's image path at once instead of a literal in each caller
  ([#1658](https://github.com/Morrison-Lab/gha/issues/1658)).
