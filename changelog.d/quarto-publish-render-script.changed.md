- `quarto-publish` runs its render step from `quarto-publish/render-site.sh` instead of an inline `run:` block.
  The step's environment and behavior are unchanged.
  A file can be handed to a cluster job, which is the next step of [gha#1563](https://github.com/Morrison-Lab/gha/issues/1563).
