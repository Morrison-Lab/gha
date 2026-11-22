- **`check-bitmap-figures`**
  (Morrison-Lab/lds#3086, a private repository):
  add a composite action and reusable workflow, diff-scoped and blocking,
  that flags a new bitmap figure where a script-generated vector graph would do.
  It flags a new `.png`, `.jpg`, `.gif`, `.bmp`, `.tif`, or `.webp` file,
  a new image reference to one,
  and a new raster figure device such as `fig-format: png` or `dev: png`.
