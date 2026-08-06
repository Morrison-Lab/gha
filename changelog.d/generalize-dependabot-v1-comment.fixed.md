- **Generalized `.github/dependabot.yml`'s first-party exemption comment** so it
  no longer names a specific major tag (#310).
  The header comment stated that first-party `Morrison-Lab/gha/*` self-references
  and the `examples/` templates "track the `@v1` major tag", but capabilities now
  pin various tags -- `@v2` for 20+ of them, `@v1` for the rest -- so the written
  rationale for the Dependabot exemption read as stale.
  It now names "their capability's major tag (see the Versioning section of
  README.md)" instead, which cannot go stale again.
  This is a comment-only change; the exemption policy itself is unchanged.
