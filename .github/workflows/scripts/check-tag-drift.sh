#!/usr/bin/env bash
# Surface when main has drifted ahead of the active major tag (e.g. v2).
#
# Derives the major tag from the latest semver release tag (vX.Y.Z) and
# calculates how many commits HEAD is ahead of that major tag.
#
# Outputs:
#   drift        - 'true' if HEAD is ahead of the major tag, 'false' otherwise
#   major        - the major tag name (e.g. 'v2')
#   drift_count  - number of commits HEAD is ahead of the major tag

set -euo pipefail

TARGET_REF="${1:-HEAD}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/resolve-major-tag.sh"

# 1. Resolve latest semver release tag (vX.Y.Z) and major tag (vX)
resolve_major_tag

if [ -z "$LATEST" ]; then
  echo "::notice::No vX.Y.Z release tag found; tag drift check skipped."
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    printf 'drift=false\nmajor=\ndrift_count=0\n' >> "$GITHUB_OUTPUT"
  fi
  exit 0
fi

# 2. Check if major tag exists in git repository
TAG_COMMIT=$(git rev-parse --verify --quiet "refs/tags/$MAJOR^{commit}" || true)

if [ -z "$TAG_COMMIT" ]; then
  echo "::notice::Major tag '$MAJOR' does not exist yet; tag drift check skipped."
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    printf 'drift=false\nmajor=%s\ndrift_count=0\n' "$MAJOR" >> "$GITHUB_OUTPUT"
  fi
  exit 0
fi

HEAD_COMMIT=$(git rev-parse --verify --quiet "$TARGET_REF^{commit}" || true)

if [ -z "$HEAD_COMMIT" ]; then
  echo "::error::Target ref '$TARGET_REF' could not be resolved to a commit."
  exit 1
fi

# 3. Calculate commit drift
DRIFT_COUNT=$(git rev-list --count "$TAG_COMMIT..$HEAD_COMMIT")

if [ "$DRIFT_COUNT" -gt 0 ]; then
  MSG="$MAJOR is $DRIFT_COUNT commit(s) behind main ($TAG_COMMIT..$HEAD_COMMIT). Run slide-major-tag.yml when ready to publish."
  echo "::notice title=Major Tag Drift Notice::$MSG"

  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    cat <<EOF >> "$GITHUB_STEP_SUMMARY"

### 🏷️ Major Tag Drift Notice

**$MAJOR** is **$DRIFT_COUNT** commit(s) behind \`main\`.
Run [\`slide-major-tag.yml\`](https://github.com/Morrison-Lab/gha/actions/workflows/slide-major-tag.yml) when ready to publish.
EOF
  fi

  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    printf 'drift=true\nmajor=%s\ndrift_count=%d\n' "$MAJOR" "$DRIFT_COUNT" >> "$GITHUB_OUTPUT"
  fi
else
  echo "::notice::$MAJOR is up to date with main."
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    printf 'drift=false\nmajor=%s\ndrift_count=0\n' "$MAJOR" >> "$GITHUB_OUTPUT"
  fi
fi
