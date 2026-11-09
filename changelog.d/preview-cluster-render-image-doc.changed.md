- **`preview`'s `cluster-render` docs say `cluster-image` is required, and a test pins the step wiring**
  ([#1622](https://github.com/Morrison-Lab/gha/issues/1622)).
  With no image the steps run bare on the execute node, which has no Quarto.
  The test now fails if the cluster plan step is renamed.
