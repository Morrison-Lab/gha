- **New `check-tag-drift` capability** (#309).
  Surfaces when `main` has unreleased commits ahead of the active major tag
  (e.g. `v2`) by emitting a GitHub Actions notice and job summary pointing to
  `slide-major-tag.yml`.
