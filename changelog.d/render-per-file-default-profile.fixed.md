- **The `per-file-formats` fallback honours the project's default profile.**
  With no `render-profile`, the render-list fallback now reads the
  `profile: default:` profile of `_quarto.yml`, as Quarto does,
  so a page that profile excludes (mds's `references.qmd`) is not rendered
  ([gha#1214](https://github.com/Morrison-Lab/gha/issues/1214)).
