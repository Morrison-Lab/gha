- **`assemble-news` now fails on a fragment whose category it does not
  recognize** (#562). The collation loop only globbed known categories, so a
  fragment such as `foo.infrastructure.md` was skipped with no diagnostic and
  left on disk, and the change it documented never reached the changelog. The
  check runs before anything is consumed, so a mixed batch fails without
  deleting the valid fragments alongside it. The composite also passes its
  inputs through `env:` rather than interpolating them into the `run:` block.
