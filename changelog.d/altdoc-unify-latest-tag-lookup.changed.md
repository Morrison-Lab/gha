- **`generate-altdoc-version-dropdown` gains a `release-tags` input** (#287).
  `altdoc-multiversion-docs.yml`'s "Determine latest stable release tag" step
  and the composite's own `generate_version_dropdown.py` used to each
  independently query `gh api repos/<repo>/releases` and derive the latest
  stable `vX.Y.Z` tag, which could drift if one implementation changed
  without the other.
  The workflow now passes its already-resolved tag list through to the
  composite via `release-tags`; when set, the composite uses that list
  as-is instead of re-deriving it.
  The composite's own gh api/git tag discovery stays as a fallback for
  standalone use (an empty `release-tags`, the default) --
  used by `_selftest.yml`'s direct composite exercises, which don't set it.
