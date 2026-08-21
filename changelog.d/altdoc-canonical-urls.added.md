- **`altdoc-multiversion-docs` now emits canonical URLs for every version
  directory** (#332).
  The workflow deploys the same rendered site to `/dev/`, `/latest-tag/`,
  `/vX.Y.Z/`, and `/pr-preview/pr-<N>/`, and nothing previously told a search
  engine which copy was authoritative --- so an archive or `/dev/` could
  outrank `/latest-tag/` and land a reader on docs for a version they are not
  running.
  Each indexable page now gets a `<link rel="canonical">` pointing at its
  `/latest-tag/` equivalent, and PR previews are marked `noindex` instead.
  A canonical is emitted only when the target actually exists on the deploy
  branch; a page with no `/latest-tag/` counterpart names its own URL rather
  than one that would 404.
  No configuration is required, and no new inputs were added.
