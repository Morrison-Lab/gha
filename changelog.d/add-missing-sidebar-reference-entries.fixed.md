- **The website's "Reference" sidebar now lists every reference page** (#273).
  Eight existing pages were missing from `website/_quarto.yml`'s sidebar, so
  they were reachable only by direct URL or via the catalog links in
  `website/workflows.qmd`: `lint-yaml`, `lint-markdown`, `check-new-line-breaks`,
  `lint-qmd`, `lint-changed-lines`, `check-equation-renders`,
  `request-dependabot-review`, and `altdoc-multiversion-docs`.
  Each is inserted at its canonical position, so the sidebar order stays
  identical to the `workflows.qmd` catalog order.
