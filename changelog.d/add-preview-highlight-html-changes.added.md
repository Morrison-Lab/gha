- **`preview`: highlight added and modified text in rendered HTML**
  ([#761](https://github.com/Morrison-Lab/gha/issues/761)).
  Set `highlight-changes: true` and the composite compares modified chapters
  against the version published on `gh-pages`,
  injecting inline marks (`preview-text-changed`, `preview-text-added`, `preview-element-added`)
  and a change summary banner on modified pages.
  Pages differing only in build metadata (such as htmlwidgets IDs or build timestamps)
  remain unmodified and byte-identical to avoid noise.
  Pages new to the PR receive a new-page banner without spurious diff highlighting.
  Opt-in and defaults off, so existing consumers remain unaffected.
