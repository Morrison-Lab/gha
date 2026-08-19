#!/usr/bin/env bash
# Resolves the latest semver release tag (vX.Y.Z) and active major tag (vX).
#
# Derives the major tag from the latest semver release tag (vX.Y.Z).
# The grep excludes pre-release tags (e.g. v2.0.0-rc1), which the glob
# would otherwise match and version-sort could rank above a stable tag.
#
# Usage:
#   source .github/workflows/scripts/resolve-major-tag.sh
#   resolve_major_tag  # sets LATEST and MAJOR variables
#
# Or executed directly:
#   bash .github/workflows/scripts/resolve-major-tag.sh
#   (prints LATEST=... and MAJOR=...)

resolve_major_tag() {
  LATEST=$(git tag --list 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname \
    | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' \
    | head -n1 || true)

  if [ -n "$LATEST" ]; then
    MAJOR="${LATEST%%.*}"
  else
    MAJOR=""
  fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  set -euo pipefail
  resolve_major_tag
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    printf 'latest=%s\nmajor=%s\n' "$LATEST" "$MAJOR" >> "$GITHUB_OUTPUT"
  fi
  echo "LATEST=$LATEST"
  echo "MAJOR=$MAJOR"
fi
